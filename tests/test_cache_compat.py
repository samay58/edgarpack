"""Compatibility tests for SEC cache helpers."""

from __future__ import annotations

import importlib.util
import sys
import types
from datetime import datetime, timezone
from pathlib import Path


def test_sec_cache_uses_timezone_utc_when_datetime_utc_is_unavailable(monkeypatch):
    fake_datetime = types.ModuleType("datetime")
    fake_datetime.datetime = datetime
    fake_datetime.timezone = timezone
    monkeypatch.setitem(sys.modules, "datetime", fake_datetime)

    module_path = Path(__file__).resolve().parents[1] / "edgarpack" / "sec" / "cache.py"
    spec = importlib.util.spec_from_file_location("_cache_compat_probe", module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    assert module.UTC is timezone.utc  # noqa: UP017 - asserting the compatibility fallback
