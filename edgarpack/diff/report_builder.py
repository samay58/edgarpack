"""Build report-ready diff models from filing packs."""

from __future__ import annotations

import difflib
import re

from .report_models import TextSpan

_TOKEN_RE = re.compile(r"\w+|\s+|[^\w\s]+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text)


def build_text_spans(old_text: str, new_text: str) -> tuple[list[TextSpan], list[TextSpan]]:
    """Return deterministic old/new token spans that reconstruct the inputs."""
    old_tokens = _tokens(old_text)
    new_tokens = _tokens(new_text)
    matcher = difflib.SequenceMatcher(None, old_tokens, new_tokens, autojunk=False)
    old_spans: list[TextSpan] = []
    new_spans: list[TextSpan] = []

    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        old_piece = "".join(old_tokens[old_start:old_end])
        new_piece = "".join(new_tokens[new_start:new_end])
        if tag == "equal":
            if old_piece:
                old_spans.append(TextSpan(side="old", op="equal", text=old_piece))
            if new_piece:
                new_spans.append(TextSpan(side="new", op="equal", text=new_piece))
        elif tag == "replace":
            if old_piece:
                old_spans.append(TextSpan(side="old", op="replace", text=old_piece))
            if new_piece:
                new_spans.append(TextSpan(side="new", op="replace", text=new_piece))
        elif tag == "delete":
            if old_piece:
                old_spans.append(TextSpan(side="old", op="delete", text=old_piece))
        elif tag == "insert":
            if new_piece:
                new_spans.append(TextSpan(side="new", op="insert", text=new_piece))

    return old_spans, new_spans
