"""Generate the CLI metric directory docs.

The live metric surface is code-owned: query/comps/compare route through
edgarpack.query.concepts, while qualitative KPI names come from
edgarpack.query.kpi_extract. This script renders a structured JSON artifact and
the human-facing Markdown guide from those sources.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from edgarpack.query.concepts import (
    CONCEPT_SCOPE_WARNINGS,
    METRIC_MAP,
    MetricMeta,
)
from edgarpack.query.kpi_extract import KPI_CATALOG, KpiDef
from edgarpack.query.layer_zero import METRIC_ALIASES
from edgarpack.query.metric_map import (
    CANONICAL_METRICS as CROSS_STANDARD_CANONICAL_METRICS,
)
from edgarpack.query.metric_map import (
    METRIC_MAP as CROSS_STANDARD_METRIC_MAP,
)
from edgarpack.query.presets import PRESETS

ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "docs" / "METRIC_DIRECTORY.json"
MARKDOWN_PATH = ROOT / "docs" / "METRIC_DIRECTORY.md"


def _component_to_json(component: str | tuple[str, int]) -> dict[str, Any]:
    if isinstance(component, tuple):
        metric, offset = component
    else:
        metric, offset = component, 0
    return {"metric": metric, "period_offset": offset}


def _metric_kind(meta: MetricMeta) -> str:
    if meta.kind == "cagr":
        return "cagr"
    if meta.derived:
        return "derived"
    return "direct"


def _concept_scope_warnings(meta: MetricMeta) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    for concept in meta.concepts + meta.ifrs_concepts:
        warning = CONCEPT_SCOPE_WARNINGS.get(concept)
        if warning:
            warnings.append({"concept": concept, "warning": warning})
    return warnings


def _metric_to_json(name: str, meta: MetricMeta) -> dict[str, Any]:
    return {
        "name": name,
        "kind": _metric_kind(meta),
        "period_shape": "duration" if meta.duration else "instant",
        "formula": meta.formula,
        "components": [_component_to_json(component) for component in meta.components],
        "concepts": {
            "us_gaap": list(meta.concepts),
            "ifrs_full": list(meta.ifrs_concepts),
        },
        "cagr": (
            {
                "years": meta.cagr_years,
                "base_metric": meta.cagr_base,
            }
            if meta.kind == "cagr"
            else None
        ),
        "scope_warnings": _concept_scope_warnings(meta),
        "queryable_via": ["query", "comps", "compare"],
    }


def _kpi_to_json(name: str, definition: KpiDef) -> dict[str, Any]:
    return {
        "name": name,
        "phrases": list(definition.phrases),
        "unit_hint": definition.unit_hint,
        "industry": list(definition.industry),
        "description": definition.description,
        "queryable_via": ["query", "comps", "compare"],
        "notes": [
            "Requires a built pack for the requested company/period.",
            "Uses Layer B KPI extraction and persists rows in learned_concepts.",
        ],
    }


def _aliases_by_metric() -> dict[str, list[str]]:
    aliases: dict[str, list[str]] = {}
    for alias, metric in sorted(METRIC_ALIASES.items(), key=lambda item: (item[1], item[0])):
        aliases.setdefault(metric, []).append(alias)
    return aliases


def build_directory() -> dict[str, Any]:
    hardcoded_metrics = [_metric_to_json(name, meta) for name, meta in METRIC_MAP.items()]
    kpi_catalog = [_kpi_to_json(name, definition) for name, definition in KPI_CATALOG.items()]
    aliases_by_metric = _aliases_by_metric()

    return {
        "schema_version": 1,
        "title": "EdgarPack CLI Metric Directory",
        "scope": {
            "included": [
                "Hardcoded XBRL-backed metrics accepted by query, comps, and compare.",
                "Derived and CAGR metrics computed from cited components.",
                "Layer 0 aliases that normalize common shorthand names.",
                "Layer B KPI catalog names that query can attempt through built packs.",
                "Presets exposed by query --preset.",
            ],
            "excluded": [
                "Company-specific discovered metrics populated by edgarpack which.",
                "Ad hoc learned_concepts rows created by self-heal for one company/filing.",
            ],
        },
        "sources": {
            "hardcoded_metrics": "edgarpack/query/concepts.py:METRIC_MAP",
            "aliases": "edgarpack/query/layer_zero.py:METRIC_ALIASES",
            "kpi_catalog": "edgarpack/query/kpi_extract.py:KPI_CATALOG",
            "learned_registry": "edgarpack/query/learned_registry.py",
            "presets": "edgarpack/query/presets.py:PRESETS",
            "cross_standard_helper": "edgarpack/query/metric_map.py",
        },
        "cli_commands": {
            "query": "edgarpack query <company> <metric_csv> --period <selector>",
            "comps": "edgarpack comps <company...> --metrics <metric_csv> --period <selector>",
            "compare": "edgarpack compare <company...> --metrics <metric_csv> --currency usd",
            "which": "edgarpack which <company> --format json",
            "learned": "edgarpack learned list",
        },
        "counts": {
            "hardcoded_metrics": len(hardcoded_metrics),
            "direct_metrics": sum(1 for item in hardcoded_metrics if item["kind"] == "direct"),
            "derived_metrics": sum(1 for item in hardcoded_metrics if item["kind"] == "derived"),
            "cagr_metrics": sum(1 for item in hardcoded_metrics if item["kind"] == "cagr"),
            "aliases": len(METRIC_ALIASES),
            "kpi_catalog_metrics": len(kpi_catalog),
            "cross_standard_canonical_metrics": len(CROSS_STANDARD_CANONICAL_METRICS),
        },
        "presets": {name: list(metrics) for name, metrics in PRESETS.items()},
        "aliases": [
            {"alias": alias, "metric": metric} for alias, metric in sorted(METRIC_ALIASES.items())
        ],
        "aliases_by_metric": aliases_by_metric,
        "hardcoded_metrics": hardcoded_metrics,
        "kpi_catalog_metrics": kpi_catalog,
        "cross_standard_helper": {
            "note": (
                "This is the smaller cross-standard helper map, not the full query/comps "
                "registry. The CLI query surface is owned by concepts.py."
            ),
            "standards": {
                standard: {metric: concepts for metric, concepts in metric_map.items()}
                for standard, metric_map in CROSS_STANDARD_METRIC_MAP.items()
            },
        },
    }


def render_json(directory: dict[str, Any]) -> str:
    return json.dumps(directory, indent=2, sort_keys=False) + "\n"


def _cell(value: str | None) -> str:
    if value is None or value == "":
        return "-"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _code(value: str) -> str:
    return f"`{value}`"


def _code_list(values: list[str], *, empty: str = "-") -> str:
    if not values:
        return empty
    return ", ".join(_code(value) for value in values)


def _compact_code_list(values: list[str], *, limit: int = 3, empty: str = "-") -> str:
    if not values:
        return empty
    visible = values[:limit]
    suffix = ""
    if len(values) > limit:
        suffix = f" (+{len(values) - limit} more in JSON)"
    return ", ".join(_code(value) for value in visible) + suffix


def _component_list(components: list[dict[str, Any]]) -> str:
    if not components:
        return "-"
    rendered: list[str] = []
    for component in components:
        metric = str(component["metric"])
        offset = int(component["period_offset"])
        suffix = "" if offset == 0 else f" ({offset:+d}y)"
        rendered.append(f"`{metric}`{suffix}")
    return ", ".join(rendered)


def _warning_list(warnings: list[dict[str, str]]) -> str:
    if not warnings:
        return "-"
    return "; ".join(f"`{item['concept']}`: {item['warning']}" for item in warnings)


def _metric_aliases(metric: str, directory: dict[str, Any]) -> list[str]:
    aliases_by_metric = directory["aliases_by_metric"]
    return list(aliases_by_metric.get(metric, []))


def _markdown_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_cell(value) for value in row) + " |")
    return lines


def render_markdown(directory: dict[str, Any]) -> str:
    counts = directory["counts"]
    hardcoded = directory["hardcoded_metrics"]
    direct_metrics = [item for item in hardcoded if item["kind"] == "direct"]
    derived_metrics = [item for item in hardcoded if item["kind"] in {"derived", "cagr"}]

    lines: list[str] = [
        "# EdgarPack CLI Metric Directory",
        "",
        "<!-- Generated by scripts/generate_metric_directory.py. Do not edit by hand. -->",
        "",
        "This is the reference guide for the metric names EdgarPack can try from the CLI. "
        "`docs/METRIC_DIRECTORY.json` is the exhaustive structured artifact generated from "
        "the same code. Use this page when you are choosing a metric; use the JSON when you "
        "need every concept tag or want to feed the registry into another tool.",
        "",
        "## At a Glance",
        "",
        f"- {counts['hardcoded_metrics']} hardcoded metrics work through `query`, `comps`, "
        "and `compare`.",
        f"- {counts['direct_metrics']} read directly from XBRL concepts.",
        f"- {counts['derived_metrics']} are computed from cited component values.",
        f"- {counts['cagr_metrics']} are FY-anchored CAGR metrics.",
        f"- {counts['aliases']} shorthand aliases normalize common inputs.",
        f"- {counts['kpi_catalog_metrics']} KPI catalog names can be attempted from built packs.",
        "",
        "## Which Surface To Use",
        "",
    ]

    lines.extend(
        _markdown_table(
            ["Need", "Use", "Why"],
            [
                [
                    "One company, known metric",
                    "`edgarpack query`",
                    "Returns cited values, JSON, links, and audit details.",
                ],
                [
                    "SEC peer comp",
                    "`edgarpack comps`",
                    "Runs the same metric list across companies in parallel.",
                ],
                [
                    "Cross-market comp",
                    "`edgarpack compare`",
                    "Adds HKEX/SSE routing and USD/native currency handling.",
                ],
                [
                    "Find company-specific KPIs",
                    "`edgarpack which`",
                    "Discovers MD&A metrics that are not global registry entries.",
                ],
                [
                    "Inspect learned/self-healed mappings",
                    "`edgarpack learned list`",
                    "Shows cached fuzzy, LLM, and KPI mappings.",
                ],
            ],
        )
    )
    lines.extend(
        [
            "",
            "## Scope",
            "",
            "- `query`, `comps`, and `compare` share the hardcoded metric map in "
            "`edgarpack/query/concepts.py`.",
            "- Shorthand names such as `rev` and `fcf` are normalized by "
            "`edgarpack/query/layer_zero.py` before lookup.",
            "- KPI catalog names such as `arr`, `nrr`, and `gmv` are known names, but they "
            "require a built pack and may need Layer B extraction before returning values.",
            "- Company-specific metrics discovered by `edgarpack which` are intentionally not "
            "enumerated here. They live in `company_kpis` / `learned_concepts` and are "
            "highest-alpha but company-local.",
            "- The file named `edgarpack/query/metric_map.py` is a smaller cross-standard helper "
            "map. It is not the exhaustive query/comps registry.",
            "",
            "## CLI Usage",
            "",
            "```bash",
            "edgarpack query NVDA revenue,gross_margin --period lfy --format json",
            "edgarpack comps NVDA AMD INTC --metrics revenue,ebitda,fcf_margin --period ltm",
            "edgarpack compare NVDA BIDU BABA --metrics revenue,gross_margin --currency usd",
            "edgarpack which FIG --format json",
            "edgarpack learned list --source kpi-llm",
            "```",
            "",
            "Use `--strict` on `query`, `comps`, or `compare` when you want only hardcoded "
            "concept-map values and want to reject learned/self-healed values.",
            "",
            "## Presets",
            "",
        ]
    )

    preset_rows = [
        [name, _code_list(list(metrics))] for name, metrics in sorted(directory["presets"].items())
    ]
    lines.extend(_markdown_table(["Preset", "Metrics"], preset_rows))
    lines.extend(
        [
            "",
            "## Aliases",
            "",
            "Aliases are conveniences, not separate metrics. They normalize into the "
            "canonical metric before lookup.",
            "",
        ]
    )

    alias_rows = [
        [_code(item["alias"]), _code(item["metric"])]
        for item in sorted(directory["aliases"], key=lambda item: (item["metric"], item["alias"]))
    ]
    lines.extend(_markdown_table(["Alias", "Canonical metric"], alias_rows))
    lines.extend(
        [
            "",
            "## Direct XBRL Metrics",
            "",
            "These are read directly from SEC companyfacts when a candidate concept exists. "
            "`concepts.py` owns the priority order. IFRS fallbacks are used for non-US filers "
            "when `us-gaap` has no usable match. The table keeps the human view compact; "
            "the JSON contains the complete concept list for every row.",
            "",
        ]
    )

    direct_rows: list[list[str]] = []
    for item in direct_metrics:
        aliases = _metric_aliases(item["name"], directory)
        concepts = item["concepts"]
        direct_rows.append(
            [
                _code(item["name"]),
                item["period_shape"],
                _code_list(aliases),
                _compact_code_list(concepts["us_gaap"]),
                _compact_code_list(concepts["ifrs_full"]),
                "yes" if item["scope_warnings"] else "-",
            ]
        )
    lines.extend(
        _markdown_table(
            ["Metric", "Shape", "Aliases", "Best US-GAAP candidates", "IFRS fallback", "Caveat"],
            direct_rows,
        )
    )

    caveat_rows: list[list[str]] = []
    for item in direct_metrics:
        for warning in item["scope_warnings"]:
            caveat_rows.append([_code(item["name"]), _code(warning["concept"]), warning["warning"]])
    if caveat_rows:
        lines.extend(
            [
                "",
                "### Direct Metric Caveats",
                "",
                "These are the concept-level places where a value can be technically "
                "available but economically broader or narrower than the metric label.",
                "",
            ]
        )
        lines.extend(_markdown_table(["Metric", "Concept", "Caveat"], caveat_rows))

    lines.extend(
        [
            "",
            "## Derived Metrics",
            "",
            "These metrics are computed only from cited component values. If a component is "
            "missing, stale, or misaligned to the requested period, the derived metric returns "
            "`None` rather than inventing a value.",
            "",
        ]
    )

    derived_rows: list[list[str]] = []
    for item in derived_metrics:
        aliases = _metric_aliases(item["name"], directory)
        derived_rows.append(
            [
                _code(item["name"]),
                item["kind"],
                item["period_shape"],
                _code_list(aliases),
                _cell(item["formula"]),
                _component_list(item["components"]),
            ]
        )
    lines.extend(
        _markdown_table(
            ["Metric", "Kind", "Shape", "Aliases", "Formula", "Components"],
            derived_rows,
        )
    )
    lines.extend(
        [
            "",
            "## KPI Catalog Metrics",
            "",
            "These names are known to the same `financials()` path used by `query`, `comps`, "
            "and `compare`, but they are not global XBRL facts. They rely on built packs and "
            "Layer B extraction from filing prose/tables. Successful extractions are persisted "
            "in `learned_concepts`; `which` can also populate `company_kpis` for "
            "company-specific discovered names.",
            "",
        ]
    )

    kpi_rows: list[list[str]] = []
    for item in directory["kpi_catalog_metrics"]:
        kpi_rows.append(
            [
                _code(item["name"]),
                item["unit_hint"],
                _code_list(item["phrases"]),
                ", ".join(item["industry"]) if item["industry"] else "-",
                item["description"] or "-",
            ]
        )
    lines.extend(
        _markdown_table(
            ["Metric", "Unit hint", "Trigger phrases", "Industry", "Description"],
            kpi_rows,
        )
    )
    lines.extend(
        [
            "",
            "## Discovered Metrics From `which`",
            "",
            "`which` is deliberately outside this static directory. It walks registered packs "
            "for one company, extracts stable MD&A KPIs, and stores slugs such as "
            "`paid_seats` or company-specific segment volumes in `company_kpis`. After that, "
            "`query` can resolve those slugs for that company without another LLM call.",
            "",
            "That means the full metric universe for a company is:",
            "",
            "1. Hardcoded metrics in this directory.",
            "2. KPI catalog names in this directory, if the company discloses them.",
            "3. Company-specific `which` discoveries in the local registry.",
            "4. Self-healed learned mappings in `learned_concepts`.",
            "",
            "For inspection:",
            "",
            "```bash",
            "edgarpack which FIG --format json",
            "edgarpack learned list --cik <CIK>",
            "```",
            "",
            "## Maintenance",
            "",
            "Regenerate after metric changes:",
            "",
            "```bash",
            "uv run python scripts/generate_metric_directory.py",
            "uv run python scripts/generate_metric_directory.py --check",
            "```",
            "",
        ]
    )

    return "\n".join(lines)


def write_outputs(directory: dict[str, Any]) -> None:
    JSON_PATH.write_text(render_json(directory), encoding="utf-8")
    MARKDOWN_PATH.write_text(render_markdown(directory), encoding="utf-8")


def check_outputs(directory: dict[str, Any]) -> list[str]:
    expected = {
        JSON_PATH: render_json(directory),
        MARKDOWN_PATH: render_markdown(directory),
    }
    mismatches: list[str] = []
    for path, content in expected.items():
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            mismatches.append(str(path.relative_to(ROOT)))
    return mismatches


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if generated metric directory docs are out of date.",
    )
    args = parser.parse_args(argv)

    directory = build_directory()
    if args.check:
        mismatches = check_outputs(directory)
        if mismatches:
            joined = ", ".join(mismatches)
            print(f"metric directory docs are out of date: {joined}", file=sys.stderr)
            return 1
        return 0

    write_outputs(directory)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
