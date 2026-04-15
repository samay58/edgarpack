from __future__ import annotations

from pathlib import Path

import yaml


def load_section_map() -> dict[str, str]:
    path = Path(__file__).parent / "sections.yaml"
    with path.open() as f:
        data = yaml.safe_load(f)
    return {k.strip().upper().rstrip("."): v for k, v in data["sections"].items()}
