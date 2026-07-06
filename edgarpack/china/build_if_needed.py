from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from ..config import DEFAULT_PACKS_DIR
from ..hk.adapter import build_hk_pack
from ..hk.extract import HKExtractionBlockedError, extract_facts_from_pack
from .pack_store import classify_china_pack


class ChinaPackNoFactsError(RuntimeError):
    pass


@dataclass(frozen=True)
class EnsurePackResult:
    ok: bool
    return_code: int
    message: str | None = None
    pack_dir: Path | None = None


@dataclass(frozen=True)
class HKBuildResult:
    pack_dir: Path
    facts_path: Path | None
    blocked_error: BaseException | None = None
    no_facts: bool = False


def _find_latest_sse_annual_report(stock_code: str) -> Any:
    from .acquire import find_latest_annual_report

    return find_latest_annual_report(stock_code)


def _synthetic_sse_company(stock_code: str) -> object:
    from ..identity import ResolvedCompany

    code = stock_code.strip()
    return ResolvedCompany(
        ticker=code,
        listing="SSE",
        source="SSE",
        cik=None,
        hk_stock_code=None,
        stock_code=code,
        aliases=(),
        private=False,
    )


def _acquire_hk_filing(client: Any, code: str) -> tuple[Any, str, list[str]]:
    from ..hk import acquire as hk

    hk.warm_up(client)
    match = hk.resolve_stock_id(client, code)
    rows = hk.list_annual_reports(client, match.stock_id)
    row = hk.select_latest_annual_report(rows, stock_code=match.code)
    ref = hk.to_filing_ref(row, stock_code=match.code)
    return ref, match.name, list(row.stock_codes)


def _replace_tree(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.move(str(src), str(dest))


async def _build_sse_query_pack(stock_code: str, pack_root: Path) -> Path:
    from ..pack.build import build_sse_pack

    selected = _find_latest_sse_annual_report(stock_code)
    company_name = selected.company_name or stock_code
    pack_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=pack_root) as tmp_dir:
        result = await build_sse_pack(
            url=selected.source_url,
            stock_code=stock_code,
            company_name=company_name,
            filing_date=selected.filing_date,
            out_dir=Path(tmp_dir),
            with_chunks=True,
            force=False,
        )
        dest = pack_root / "sse" / stock_code / result.output_dir.name
        _replace_tree(result.output_dir, dest)
    return dest


def build_hk_latest_pack(
    code: str,
    packs_root: Path = DEFAULT_PACKS_DIR,
    *,
    publish_debug_on_failure: bool = False,
) -> HKBuildResult:
    client = httpx.Client(
        headers={"User-Agent": "edgarpack/0.1 (+https://github.com)"},
        follow_redirects=True,
        timeout=120.0,
    )
    tmp_dir: Path | None = None
    target: Path | None = None
    try:
        ref, company_name, dual_codes = _acquire_hk_filing(client, code)
        target = packs_root / "hk" / ref.stock_code / f"{ref.stock_code}_{ref.fiscal_year}"
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp_dir = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))
        pack = build_hk_pack(
            ref,
            tmp_dir,
            company_name=company_name,
            dual_counter_codes=dual_codes,
            client=client,
        )
        try:
            facts_path = extract_facts_from_pack(pack.path)
        except HKExtractionBlockedError as exc:
            if publish_debug_on_failure and target is not None:
                _replace_tree(pack.path, target)
                tmp_dir = None
                return HKBuildResult(pack_dir=target, facts_path=None, blocked_error=exc)
            raise
        if facts_path is None:
            if publish_debug_on_failure and target is not None:
                _replace_tree(pack.path, target)
                tmp_dir = None
                return HKBuildResult(pack_dir=target, facts_path=None, no_facts=True)
            raise ChinaPackNoFactsError(f"HKEX facts extraction produced no facts for {code}")
        _replace_tree(pack.path, target)
        tmp_dir = None
        return HKBuildResult(pack_dir=target, facts_path=target / facts_path.name)
    finally:
        client.close()
        if tmp_dir is not None and tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)


def _build_hk_query_pack(code: str, packs_root: Path) -> Path:
    return build_hk_latest_pack(code, packs_root, publish_debug_on_failure=False).pack_dir


def _target_for_query(company_input: str, resolved: object | None) -> object | None:
    from ..identity import looks_like_china_a_share_code

    source = str(getattr(resolved, "source", "") or "") if resolved is not None else ""
    if source in {"SSE", "HKEX"}:
        return resolved
    if source:
        return None
    if looks_like_china_a_share_code(company_input):
        return _synthetic_sse_company(company_input)
    return None


async def ensure_china_pack_for_query(
    *,
    company_input: str,
    resolved: object | None,
    pack_root: Path | None = None,
) -> EnsurePackResult:
    target = _target_for_query(company_input, resolved)
    if target is None:
        return EnsurePackResult(ok=True, return_code=0)

    root = Path(pack_root or DEFAULT_PACKS_DIR)
    source = str(getattr(target, "source", "") or "")
    stock_code = str(
        getattr(target, "stock_code", None)
        or getattr(target, "hk_stock_code", None)
        or company_input
    ).strip()
    status = classify_china_pack(target, root)
    if status.kind == "queryable":
        return EnsurePackResult(ok=True, return_code=0, pack_dir=status.pack_dir)
    if status.kind == "built_without_facts":
        return EnsurePackResult(
            ok=False,
            return_code=1,
            message=(
                f"Pack for {stock_code} was built but no facts were extracted; "
                "see the build warnings (rebuild with --force after fixing)."
            ),
            pack_dir=status.pack_dir,
        )

    if source == "SSE":
        message = (
            f"No local pack for {stock_code}; fetching the latest annual report from CNINFO "
            "(typically 2-4 minutes)..."
        )
        try:
            pack_dir = await _build_sse_query_pack(stock_code, root)
        except Exception as exc:
            return EnsurePackResult(
                ok=False,
                return_code=1,
                message=f"{message}\nError: {exc}",
            )
        return EnsurePackResult(ok=True, return_code=0, message=message, pack_dir=pack_dir)

    if source == "HKEX":
        message = (
            f"No local HKEX pack for {stock_code}; fetching the latest annual report from "
            "HKEX news (typically 1-3 minutes)..."
        )
        try:
            pack_dir = _build_hk_query_pack(stock_code, root)
        except Exception as exc:
            return EnsurePackResult(
                ok=False,
                return_code=1,
                message=f"{message}\nError: {exc}",
            )
        return EnsurePackResult(ok=True, return_code=0, message=message, pack_dir=pack_dir)

    return EnsurePackResult(ok=True, return_code=0)
