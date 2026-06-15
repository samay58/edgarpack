"""HTML cleaning and sanitization.

Avoids heavy HTML/DOM dependencies so parsing stays portable while preserving
visible text deterministically.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from html import escape
from html.parser import HTMLParser

logger = logging.getLogger(__name__)

# Tags to completely remove (including content)
REMOVE_TAGS = {
    "script",
    "style",
    "noscript",
    "nav",
    "header",
    "footer",
    "iframe",
    "object",
    "embed",
    "meta",
    "link",
    "base",
    "img",
}

# HTML void elements (no end tag in normal HTML)
VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}

_ZERO_CSS_VALUE_RE = re.compile(r"^\s*0(?:\.0+)?(?:px|pt|em|rem|%)?\s*$", re.IGNORECASE)
_NEGATIVE_CSS_VALUE_RE = re.compile(r"^\s*-\d", re.IGNORECASE)


def _style_declarations(style: str) -> dict[str, str]:
    declarations: dict[str, str] = {}
    for part in style.split(";"):
        if ":" not in part:
            continue
        name, value = part.split(":", 1)
        name = name.strip().lower()
        if not name:
            continue
        declarations[name] = value.strip()
    return declarations


def _is_zero_css_value(value: str | None) -> bool:
    return bool(value and _ZERO_CSS_VALUE_RE.match(value))


def is_hidden_style(style: str) -> bool:
    """Return True when inline CSS likely hides the element visually."""
    if not style:
        return False
    declarations = _style_declarations(style)
    display = declarations.get("display", "").strip().lower()
    if display == "none":
        return True
    visibility = declarations.get("visibility", "").strip().lower()
    if visibility == "hidden":
        return True
    if _is_zero_css_value(declarations.get("width")):
        return True
    if _is_zero_css_value(declarations.get("height")):
        return True
    if _is_zero_css_value(declarations.get("opacity")):
        return True
    if declarations.get("position", "").strip().lower() == "absolute" and (
        _NEGATIVE_CSS_VALUE_RE.match(declarations.get("left", ""))
        or _NEGATIVE_CSS_VALUE_RE.match(declarations.get("top", ""))
    ):
        return True
    # font-size:0 is only a hide signal when paired with another zero-size cue.
    if _is_zero_css_value(declarations.get("font-size")):
        return any(
            _is_zero_css_value(declarations.get(prop)) for prop in ("width", "height", "opacity")
        )
    return False


def is_hidden_element(attributes: dict[str, str] | None) -> bool:
    """Return True when an element should be considered hidden.

    This is intentionally conservative: only explicit inline style or HTML 'hidden'
    attribute triggers removal.
    """
    if not attributes:
        return False
    if "hidden" in {k.lower() for k in attributes.keys()}:
        return True
    aria_hidden = (attributes.get("aria-hidden") or "").strip().lower()
    if aria_hidden in {"true", "1"}:
        return True
    return is_hidden_style(attributes.get("style", ""))


def clean_html(html: str, *, preserve_images: bool = False) -> str:
    """Clean HTML by removing scripts, styles, hidden content, and normalizing.

    Catches the parser errors HTMLParser actually raises on malformed filings
    so cleaning is best-effort. Unexpected exceptions bubble up.
    """
    parser = _CleaningHTMLParser(preserve_images=preserve_images)
    try:
        parser.feed(html)
        parser.close()
    except (AssertionError, UnicodeDecodeError) as e:
        logger.warning("clean_html: parser failed on malformed input: %s", e)

    result = "".join(parser.out)
    return _normalize_whitespace(result)


def _normalize_whitespace(html: str) -> str:
    """Normalize whitespace in HTML.

    - Collapse multiple spaces/tabs to single space
    - Preserve meaningful newlines
    - Remove leading/trailing whitespace from lines
    """
    html = html.replace("\t", " ")
    html = html.replace("\r\n", "\n").replace("\r", "\n")
    html = re.sub(r" +", " ", html)
    html = re.sub(r"\n{3,}", "\n\n", html)
    html = re.sub(r" *\n *", "\n", html)
    return html.strip()


def extract_text(html: str) -> str:
    """Extract visible text content from HTML."""
    cleaned = clean_html(html)
    parser = _TextHTMLParser()
    try:
        parser.feed(cleaned)
        parser.close()
    except Exception:
        pass
    text = "".join(parser.out)
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class _TagContext:
    tag: str
    skip_depth_delta: int


class _CleaningHTMLParser(HTMLParser):
    """Streaming HTML cleaner that removes unwanted/hidden subtrees and strips attributes."""

    def __init__(self, *, preserve_images: bool = False) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._skip_depth = 0
        self._remove_tags = REMOVE_TAGS - {"img"} if preserve_images else REMOVE_TAGS

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_l = tag.lower()

        if self._skip_depth > 0:
            if tag_l not in VOID_TAGS:
                self._skip_depth += 1
            return

        attr_dict = {k: (v if v is not None else "") for k, v in attrs}

        if tag_l in self._remove_tags:
            if tag_l not in VOID_TAGS:
                self._skip_depth = 1
            return

        if is_hidden_element(attr_dict):
            if tag_l not in VOID_TAGS:
                self._skip_depth = 1
            return

        # Strip unwanted attributes
        kept: dict[str, str] = {}
        for name, value in attr_dict.items():
            name_l = name.lower()
            if name_l in {"class", "id", "style"}:
                continue
            if name_l.startswith("on"):
                continue
            if name_l.startswith("data-"):
                continue
            kept[name_l] = value

        attrs_rendered = ""
        if kept:
            parts = [f'{k}="{escape(v, quote=True)}"' for k, v in sorted(kept.items()) if v != ""]
            if parts:
                attrs_rendered = " " + " ".join(parts)

        self.out.append(f"<{tag_l}{attrs_rendered}>")

    def handle_endtag(self, tag: str) -> None:
        tag_l = tag.lower()

        if self._skip_depth > 0:
            self._skip_depth -= 1
            if self._skip_depth < 0:
                self._skip_depth = 0
            return

        if tag_l in VOID_TAGS:
            return

        # Keep end tags for structural tags (even if unknown; md_render will strip later)
        self.out.append(f"</{tag_l}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Treat as start + end for void tags.
        self.handle_starttag(tag, attrs)
        if tag.lower() not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0 or not data:
            return
        self.out.append(data)

    def handle_comment(self, data: str) -> None:
        # Drop comments for determinism / noise.
        return


class _TextHTMLParser(HTMLParser):
    """Extract text while inserting separators at common block boundaries."""

    _BLOCK_TAGS = {
        "p",
        "div",
        "section",
        "article",
        "main",
        "header",
        "footer",
        "nav",
        "br",
        "hr",
        "tr",
        "td",
        "th",
        "li",
        "ul",
        "ol",
        "table",
        "thead",
        "tbody",
        "tfoot",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "pre",
        "blockquote",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self._BLOCK_TAGS:
            self.out.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._BLOCK_TAGS:
            self.out.append(" ")

    def handle_data(self, data: str) -> None:
        if data:
            self.out.append(data)
