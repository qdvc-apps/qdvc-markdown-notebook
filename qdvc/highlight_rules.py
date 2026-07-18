"""
highlight_rules.py — toolkit-independent markdown highlighting rules.

PURE module (no GTK): holds the regexes, tag names, and colour/weight specs that
drive the lightweight markdown highlighter, so the GTK3 and GTK4 highlighters
share one definition of *what* to highlight and only differ in *how* they apply
tags to their toolkit's text buffer (spec §14 — toolkit-independent logic lives
in the pure layer).

The design is deliberately simple and line-oriented (see docs/MAINTENANCE.md):
no external markdown library, because the requirement is a monospace view with
no font-size variation — just visual cues.

A tag spec is a dict of style attributes using toolkit-neutral names:
    foreground / background : colour strings
    bold                    : True for bold weight
    italic                  : True for italic style
    underline               : True for a single underline
The highlighters translate these into their toolkit's tag properties.
"""

import re

# Heading colours: H1 (navy) shading to progressively lighter blues for H6.
HEADING_SHADES = (
    "#204a87",  # H1
    "#3465a4",  # H2
    "#5079b8",  # H3
    "#6a8fc7",  # H4
    "#8aa8d6",  # H5
    "#a8c0e2",  # H6
)

# Tag specs keyed by tag name. Heading1..6 are generated from HEADING_SHADES.
TAG_SPECS = {f"heading{i}": {"foreground": shade, "bold": True}
             for i, shade in enumerate(HEADING_SHADES, start=1)}
TAG_SPECS.update({
    "blockquote": {"foreground": "#5c3566", "italic": True},
    "list": {"foreground": "#a40000", "bold": True},
    "hr": {"foreground": "#888888"},
    "code_inline": {"foreground": "#ce5c00", "background": "#f0f0f0"},
    "code_block": {"foreground": "#4e9a06", "background": "#f5f5f5"},
    "bold": {"bold": True},
    "italic": {"italic": True},
    "link": {"foreground": "#3465a4", "underline": True},
})

# Names of the code tags whose font follows the user's code-font setting.
CODE_TAG_NAMES = ("code_inline", "code_block")

# All tag names, in a stable order (for clear-all passes).
ALL_TAG_NAMES = tuple(
    [f"heading{i}" for i in range(1, 7)]
    + ["blockquote", "list", "hr", "code_inline", "code_block",
       "bold", "italic", "link"]
)

# Heading rule: captures the leading #'s in group 1 so the level (and colour)
# can be derived from their count.
HEADING_RGX = re.compile(r"^(#{1,6})\s.*$")

# Line-level rules: (tag_name, compiled_regex).
LINE_RULES = (
    ("blockquote", re.compile(r"^\s*>.*$")),
    ("list", re.compile(r"^\s*([-*+]|\d+\.)\s")),
    ("hr", re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")),
)

# Italics: *asterisk* form (no '*' inside) or _underscore_ form (word-bounded,
# no '_' inside), never the doubled bold delimiters.
_ITALIC = (r"(?<!\*)\*(?!\*)([^*\n]+?)\*(?!\*)"
           r"|(?<![\w])_(?!_)([^_\n]+?)_(?![\w])")

# Inline rules: (tag_name, compiled_regex).
INLINE_RULES = (
    ("code_inline", re.compile(r"`[^`\n]+`")),
    ("bold", re.compile(r"(\*\*|__)(?=\S)(.+?\S)\1")),
    ("italic", re.compile(_ITALIC)),
    ("link", re.compile(r"\[[^\]]+\]\([^)]+\)")),
)


def iter_spans(text):
    """
    Yield (tag_name, start_offset, end_offset) spans for `text`, in the order a
    highlighter should apply them (fenced code, then per-line heading/line/inline
    rules). Offsets are character offsets into `text`. Pure: no GTK, so this is
    directly unit-testable.

    Fenced code blocks (```-delimited) are tagged whole-line with "code_block";
    the fence lines themselves are included.
    """
    offset = 0
    in_fence = False
    for line in text.split("\n"):
        line_len = len(line)
        fence = line.lstrip().startswith("```")
        if fence:
            in_fence = not in_fence
            yield ("code_block", offset, offset + line_len)
        elif in_fence:
            yield ("code_block", offset, offset + line_len)
        else:
            hmatch = HEADING_RGX.match(line)
            if hmatch:
                level = min(len(hmatch.group(1)), 6)
                yield (f"heading{level}",
                       offset + hmatch.start(), offset + hmatch.end())
            for tag_name, rgx in LINE_RULES:
                m = rgx.match(line)
                if m:
                    yield (tag_name, offset + m.start(), offset + m.end())
            for tag_name, rgx in INLINE_RULES:
                for m in rgx.finditer(line):
                    yield (tag_name, offset + m.start(), offset + m.end())
        offset += line_len + 1  # +1 for the '\n' split removed
