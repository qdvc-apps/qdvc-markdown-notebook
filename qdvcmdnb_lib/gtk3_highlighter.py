"""
highlighter.py — lightweight, regex-based markdown syntax highlighting.

Applies colour/weight/style tags to a Gtk.TextBuffer. No external markdown
library is used: the requirement is a monospace view with *no font-size
variation*, just visual cues. See MAINTENANCE.md for the algorithm notes.
"""

import re

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Pango  # noqa: E402


class MarkdownHighlighter:
    """
    Applies syntax-highlighting tags to a Gtk.TextBuffer.

    Deliberately simple and line-oriented. Re-highlighting is done on the whole
    buffer, which is fine for typical note sizes.
    """

    def __init__(self, buffer, code_font="monospace 11"):
        # Hold the Gtk.TextBuffer we colour, create our style tags once, and
        # precompile the regexes used to find markdown constructs. (A
        # Gtk.TextBuffer stores text plus "tags" that style ranges of it.)
        self.buffer = buffer
        self._code_font = code_font
        self._make_tags()
        self.set_code_font(code_font)

        # Compile once. Each entry: (tag_name, compiled_regex, group_index)
        # group_index None means "whole match".
        self.line_rules = [
            ("heading", re.compile(r"^#{1,6}\s.*$"), None),
            ("blockquote", re.compile(r"^\s*>.*$"), None),
            ("list", re.compile(r"^\s*([-*+]|\d+\.)\s"), None),
            ("hr", re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$"), None),
        ]
        self.inline_rules = [
            ("code_inline", re.compile(r"`[^`\n]+`"), None),
            ("bold", re.compile(r"(\*\*|__)(?=\S)(.+?\S)\1"), None),
            ("italic", re.compile(r"(?<!\*)\*(?!\*)(\S.*?\S|\S)\*(?!\*)"), None),
            ("link", re.compile(r"\[[^\]]+\]\([^)]+\)"), None),
        ]

    def _make_tags(self):
        # Define the styling tags on the buffer's tag table (the registry of all
        # tags). Each tag carries text-style properties (colour, weight, …) that
        # GTK applies wherever the tag is later attached. `ensure` is idempotent:
        # table.lookup returns an existing tag (so re-running is harmless), and
        # create_tag(name, **props) makes a new one. The Pango.* enums are GTK's
        # font weight/style/underline constants.
        table = self.buffer.get_tag_table()

        def ensure(name, **props):
            tag = table.lookup(name)
            if tag is None:
                tag = self.buffer.create_tag(name, **props)
            return tag

        # Colours chosen to read well on a light (Pluma-like) background.
        ensure("heading", foreground="#204a87", weight=Pango.Weight.BOLD)
        ensure("blockquote", foreground="#5c3566", style=Pango.Style.ITALIC)
        ensure("list", foreground="#a40000", weight=Pango.Weight.BOLD)
        ensure("hr", foreground="#888888")
        ensure("code_inline", foreground="#ce5c00", background="#f0f0f0")
        ensure("code_block", foreground="#4e9a06", background="#f5f5f5")
        ensure("bold", weight=Pango.Weight.BOLD)
        ensure("italic", style=Pango.Style.ITALIC)
        ensure("link", foreground="#3465a4", underline=Pango.Underline.SINGLE)

    def set_code_font(self, font_desc_str):
        """
        Set the font used for inline code and fenced code blocks. Accepts a
        Pango font-description string (e.g. "DejaVu Sans Mono 11"). Applied to
        the existing tags so already-highlighted text updates immediately.
        """
        self._code_font = font_desc_str
        table = self.buffer.get_tag_table()
        for name in ("code_inline", "code_block"):
            tag = table.lookup(name)
            if tag is not None:
                tag.set_property("font", font_desc_str)

    def highlight(self):
        buf = self.buffer
        start = buf.get_start_iter()
        end = buf.get_end_iter()

        # Clear all tags first.
        for name in ("heading", "blockquote", "list", "hr",
                     "code_inline", "code_block", "bold", "italic", "link"):
            buf.remove_tag_by_name(name, start, end)

        text = buf.get_text(start, end, True)
        lines = text.split("\n")

        in_fence = False
        offset = 0  # character offset of the start of the current line
        for line in lines:
            line_len = len(line)
            line_start = buf.get_iter_at_offset(offset)
            line_end = buf.get_iter_at_offset(offset + line_len)

            fence = line.lstrip().startswith("```")
            if fence:
                in_fence = not in_fence
                buf.apply_tag_by_name("code_block", line_start, line_end)
            elif in_fence:
                buf.apply_tag_by_name("code_block", line_start, line_end)
            else:
                # Line-level rules.
                for tag_name, rgx, _ in self.line_rules:
                    if rgx_match := rgx.match(line):
                        s = buf.get_iter_at_offset(offset + rgx_match.start())
                        e = buf.get_iter_at_offset(offset + rgx_match.end())
                        buf.apply_tag_by_name(tag_name, s, e)
                # Inline rules.
                for tag_name, rgx, _ in self.inline_rules:
                    for m in rgx.finditer(line):
                        s = buf.get_iter_at_offset(offset + m.start())
                        e = buf.get_iter_at_offset(offset + m.end())
                        buf.apply_tag_by_name(tag_name, s, e)

            offset += line_len + 1  # +1 for the '\n' we split on
