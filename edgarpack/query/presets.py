"""Named metric presets for `edgarpack query --preset ...`.

A preset expands to a curated list of metrics. When combined with
``--metrics``, the preset comes first and ``--metrics`` is appended with
duplicates removed while preserving order.
"""

from __future__ import annotations

PRESETS: dict[str, tuple[str, ...]] = {
    "perf": (
        "revenue",
        "revenue_growth_yoy",
        "revenue_cagr_3y",
        "gross_margin",
        "operating_margin",
        "net_margin",
        "r_and_d_intensity",
        "sga_intensity",
        "fcf_margin",
    ),
}


def expand_metrics(metrics_csv: str | None, preset: str | None) -> list[str] | None:
    """Combine ``--preset`` and ``--metrics`` into a flat, ordered, deduped list.

    - Returns ``None`` when both inputs are absent so callers can fall through
      to the existing "all metrics" behavior.
    - Preset metrics come first; explicit ``--metrics`` entries follow.
    - Duplicates are removed while preserving first-seen order.

    Raises ``ValueError`` for an unknown preset name.
    """
    result: list[str] = []
    seen: set[str] = set()

    if preset:
        key = preset.strip().lower()
        if key not in PRESETS:
            known = ", ".join(sorted(PRESETS.keys()))
            raise ValueError(f"unknown preset {preset!r}; known presets: {known}")
        for m in PRESETS[key]:
            if m not in seen:
                seen.add(m)
                result.append(m)

    if metrics_csv:
        for raw in metrics_csv.split(","):
            m = raw.strip()
            if not m or m in seen:
                continue
            seen.add(m)
            result.append(m)

    if not result:
        return None
    return result
