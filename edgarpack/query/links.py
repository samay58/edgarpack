"""Terminal link rendering helpers for citation output."""

from __future__ import annotations

import os
import sys
from typing import IO

_OSC8_ENABLED_TERMS = {
    "iTerm.app",
    "WezTerm",
    "ghostty",
    "Ghostty",
    "Apple_Terminal",
    "vscode",
    "Warp",
}


def osc8(url: str, label: str) -> str:
    if not url:
        return label
    return f"\x1b]8;;{url}\x1b\\{label}\x1b]8;;\x1b\\"


def supports_osc8(stream: IO[str] | None = None) -> bool:
    s = stream if stream is not None else sys.stdout
    if not hasattr(s, "isatty") or not s.isatty():
        return False
    if os.environ.get("NO_COLOR"):
        return False
    term_program = os.environ.get("TERM_PROGRAM", "")
    if term_program in _OSC8_ENABLED_TERMS:
        return True
    term = os.environ.get("TERM", "")
    return term.startswith("xterm")


def compact_url(url: str) -> str:
    if not url:
        return url
    for prefix in ("https://www.", "http://www.", "https://", "http://"):
        if url.startswith(prefix):
            return url[len(prefix) :]
    return url
