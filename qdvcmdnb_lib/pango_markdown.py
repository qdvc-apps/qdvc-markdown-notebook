"""
pango_markdown.py — render a subset of Markdown to Pango markup.

Pango markup is GTK's inline-styling string format (a small HTML-like subset:
<b>, <i>, <tt>, <span>, <s>, <u>, plus size/weight/foreground attributes). It has
no block layout, so block structure (headings, lists, blockquotes, code blocks,
rules) is approximated with font sizing, weight, bullet/prefix characters, and
blank lines.

This module is pure text→text and imports no GTK, so it is unit-testable without
a display. The output is intended to be fed to Gtk.Label.set_markup or a
TextBuffer.insert_markup.

Deliberately lightweight: this mirrors the highlighter's "good enough" philosophy
rather than implementing a full CommonMark parser.
"""

import re
from xml.sax.saxutils import escape as _xml_escape

# Inline patterns, applied to already-escaped text.
_CODE_RE = re.compile(r"`([^`\n]+)`")
_BOLD_RE = re.compile(r"(\*\*|__)(?=\S)(.+?\S)\1")
_ITALIC_RE = re.compile(r"(?<![\*_\w])([*_])(?=\S)(.+?\S)\1(?![\*_\w])")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

# Heading sizes (Pango relative sizes) for levels 1..6.
_HEADING_SIZE = {
    1: "xx-large",
    2: "x-large",
    3: "large",
    4: "medium",
    5: "medium",
    6: "small",
}

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_HR_RE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
_ULIST_RE = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_OLIST_RE = re.compile(r"^(\s*)(\d+)\.\s+(.*)$")
_QUOTE_RE = re.compile(r"^\s*>\s?(.*)$")
_FENCE_RE = re.compile(r"^\s*```")


def _inline(text):
    """Escape XML special chars then apply inline markdown → Pango markup."""
    out = _xml_escape(text)
    # Inline code first (its contents should not be further interpreted). The
    # captured group is already escaped, which is what we want inside <tt>.
    out = _CODE_RE.sub(
        lambda m: f"<tt><span background='#f0f0f0'>{m.group(1)}</span></tt>",
        out)
    out = _BOLD_RE.sub(lambda m: f"<b>{m.group(2)}</b>", out)
    out = _ITALIC_RE.sub(lambda m: f"<i>{m.group(2)}</i>", out)
    # Links: show the link text, underlined and coloured; the URL is dropped from
    # the visible text (Pango markup can't make clickable links on its own).
    out = _LINK_RE.sub(
        lambda m: f"<span foreground='#3465a4' underline='single'>"
                  f"{m.group(1)}</span>",
        out)
    return out


def render(text):
    """
    Convert Markdown `text` to a Pango markup string. Always returns valid
    markup (the result is safe to pass to set_markup).
    """
    lines = text.split("\n")
    out = []
    in_fence = False
    fence_buf = []

    def flush_fence():
        if fence_buf:
            body = _xml_escape("\n".join(fence_buf))
            out.append(
                f"<tt><span background='#f5f5f5'>{body}</span></tt>")
            fence_buf.clear()

    for line in lines:
        if _FENCE_RE.match(line):
            if in_fence:
                flush_fence()
                in_fence = False
            else:
                in_fence = True
            continue
        if in_fence:
            fence_buf.append(line)
            continue

        if _HR_RE.match(line):
            out.append("<span foreground='#888888'>"
                       "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500</span>")
            continue

        m = _HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            size = _HEADING_SIZE.get(level, "medium")
            out.append(
                f"<span size='{size}' weight='bold' foreground='#204a87'>"
                f"{_inline(m.group(2))}</span>")
            continue

        m = _ULIST_RE.match(line)
        if m:
            indent = "    " * (len(m.group(1)) // 2)
            out.append(f"{indent}\u2022 {_inline(m.group(2))}")
            continue

        m = _OLIST_RE.match(line)
        if m:
            indent = "    " * (len(m.group(1)) // 2)
            out.append(f"{indent}{m.group(2)}. {_inline(m.group(3))}")
            continue

        m = _QUOTE_RE.match(line)
        if m:
            out.append(
                f"<span foreground='#5c3566'>\u2503 "
                f"<i>{_inline(m.group(1))}</i></span>")
            continue

        if line.strip() == "":
            out.append("")
            continue

        out.append(_inline(line))

    if in_fence:  # unterminated fence: render what we have
        flush_fence()

    return "\n".join(out)
