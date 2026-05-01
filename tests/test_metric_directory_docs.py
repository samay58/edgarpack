from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "scripts" / "generate_metric_directory.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location("generate_metric_directory", GENERATOR_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_metric_directory_docs_are_current() -> None:
    generator = _load_generator()
    directory = generator.build_directory()

    assert (ROOT / "docs" / "METRIC_DIRECTORY.json").read_text(encoding="utf-8") == (
        generator.render_json(directory)
    )
    assert (ROOT / "docs" / "METRIC_DIRECTORY.md").read_text(encoding="utf-8") == (
        generator.render_markdown(directory)
    )


def test_metric_directory_declares_static_and_dynamic_boundaries() -> None:
    generator = _load_generator()
    directory = generator.build_directory()

    hardcoded_names = {item["name"] for item in directory["hardcoded_metrics"]}
    kpi_names = {item["name"] for item in directory["kpi_catalog_metrics"]}
    excluded = " ".join(directory["scope"]["excluded"])

    assert {"revenue", "gross_margin", "free_cash_flow"}.issubset(hardcoded_names)
    assert {"arr", "nrr", "gmv"}.issubset(kpi_names)
    assert "edgarpack which" in excluded
