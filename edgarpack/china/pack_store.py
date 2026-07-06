from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ..config import DEFAULT_PACKS_DIR

logger = logging.getLogger(__name__)

ChinaPackKind = Literal["queryable", "missing", "built_without_facts"]

_CHINA_PACK_ROOT_ENV_WARNED: set[str] = set()


@dataclass(frozen=True)
class ChinaPackStatus:
    kind: ChinaPackKind
    pack_dir: Path | None = None
    reason: str | None = None


def _china_stock_code(resolved: object) -> str:
    stock_code = getattr(resolved, "stock_code", None) or getattr(resolved, "hk_stock_code", None)
    return str(stock_code or "").strip()


def _roots(pack_root: Path | None) -> list[Path]:
    if pack_root is not None:
        return [Path(pack_root)]
    return [DEFAULT_PACKS_DIR, Path(".")]


def _exchange_dirs(source: str) -> list[str]:
    if source == "SSE":
        return ["sse"]
    if source == "HKEX":
        return ["hk", "hkex"]
    return [source.lower()] if source else []


def _variants(resolved: object) -> list[str]:
    stock_code = _china_stock_code(resolved)
    ticker = str(getattr(resolved, "ticker", "") or "")
    seen: set[str] = set()
    values: list[str] = []
    for value in (stock_code, stock_code.lstrip("0"), ticker, ticker.upper()):
        if value and value not in seen:
            seen.add(value)
            values.append(value)
    return values


def _facts_are_queryable(facts_path: Path) -> bool:
    try:
        data = json.loads(facts_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    facts = data.get("facts") if isinstance(data, dict) else None
    if not isinstance(facts, dict):
        return False
    for concepts in facts.values():
        if isinstance(concepts, dict) and concepts:
            return True
    return False


def _sort_key(path: Path) -> tuple[str, str]:
    manifest_path = path / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            filing = manifest.get("filing", {}) if isinstance(manifest, dict) else {}
            return (str(filing.get("filing_date") or ""), str(path))
        except Exception:
            pass
    return (path.name, str(path))


def _pack_dirs_under_base(base: Path) -> list[Path]:
    if not base.exists():
        return []
    return [child for child in base.iterdir() if child.is_dir()]


def _standard_pack_dirs(resolved: object, pack_root: Path | None) -> list[Path]:
    source = str(getattr(resolved, "source", "") or "").upper()
    variants = _variants(resolved)
    candidates: list[Path] = []
    for root in _roots(pack_root):
        for exchange_dir in _exchange_dirs(source):
            for variant in variants:
                candidates.extend(_pack_dirs_under_base(root / exchange_dir / variant))
        if source == "SSE":
            stock_code = _china_stock_code(resolved)
            if stock_code:
                candidates.extend(_pack_dirs_under_base(root / "sse" / stock_code))
    return candidates


def _flat_override_pack_dirs(resolved: object) -> list[Path]:
    source = str(getattr(resolved, "source", "") or "").upper()
    china_pack_root = os.environ.get("EDGARPACK_CHINA_PACK_ROOT")
    if not china_pack_root or source != "HKEX":
        return []
    if "EDGARPACK_CHINA_PACK_ROOT" not in _CHINA_PACK_ROOT_ENV_WARNED:
        _CHINA_PACK_ROOT_ENV_WARNED.add("EDGARPACK_CHINA_PACK_ROOT")
        logger.warning(
            "EDGARPACK_CHINA_PACK_ROOT override active: China pack discovery is redirected to %s",
            china_pack_root,
        )
    root_dir = Path(china_pack_root)
    if not root_dir.is_dir():
        return []

    names: set[str] = set()
    for alias in getattr(resolved, "aliases", ()):
        alias_text = str(alias).lower()
        names.add(alias_text.replace(" ", "_"))
        names.add(alias_text)
    names.update(v.lower() for v in _variants(resolved))

    candidates: list[Path] = []
    for child in sorted(root_dir.iterdir()):
        match = re.fullmatch(r"(?P<name>.+)_(?P<fy>\d{4})", child.name)
        if match is None:
            continue
        if match.group("name").lower() in names:
            candidates.append(child)
    return candidates


def _candidate_pack_dirs(resolved: object, pack_root: Path | None) -> list[Path]:
    return sorted(
        set([*_standard_pack_dirs(resolved, pack_root), *_flat_override_pack_dirs(resolved)]),
        key=_sort_key,
        reverse=True,
    )


def discover_china_pack(resolved: object, pack_root: Path | None = None) -> Path | None:
    status = classify_china_pack(resolved, pack_root)
    return status.pack_dir if status.kind == "queryable" else None


def classify_china_pack(
    resolved: object,
    pack_root: Path | None = None,
) -> ChinaPackStatus:
    candidates = _candidate_pack_dirs(resolved, pack_root)
    if not candidates:
        return ChinaPackStatus("missing")

    for pack_dir in candidates:
        facts_path = pack_dir / "facts.json"
        if facts_path.exists() and _facts_are_queryable(facts_path):
            return ChinaPackStatus("queryable", pack_dir=pack_dir)

    return ChinaPackStatus(
        "built_without_facts",
        pack_dir=candidates[0],
        reason="pack exists but no queryable facts.json was found",
    )
