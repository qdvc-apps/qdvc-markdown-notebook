"""
gtk4_highlighter.py — markdown syntax highlighting for a GTK 4 Gtk.TextBuffer.

Mirrors qdvc/gtk3/gtk3_highlighter.py but for GTK 4. The *rules* (regexes, tag
names, colours) live in the pure ``qdvc.highlight_rules`` module and are shared
with the GTK 3 highlighter (spec §14); this class only translates those rules
into GTK 4 text-buffer tags. The GTK 4 TextBuffer tag API is the same as GTK 3's
(create_tag / apply_tag_by_name / remove_tag_by_name / get_iter_at_offset), so
the tagging code is nearly identical.
"""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Pango  # noqa: E402

from .. import highlight_rules as rules


class MarkdownHighlighter:
    """Applies syntax-highlighting tags to a GTK 4 Gtk.TextBuffer."""

    def __init__(self, buffer, code_font="monospace 11"):
        self.buffer = buffer
        self._code_font = code_font
        self._make_tags()
        self.set_code_font(code_font)

    def _make_tags(self):
        table = self.buffer.get_tag_table()

        def ensure(name, spec):
            tag = table.lookup(name)
            if tag is not None:
                return tag
            props = {}
            if "foreground" in spec:
                props["foreground"] = spec["foreground"]
            if "background" in spec:
                props["background"] = spec["background"]
            if spec.get("bold"):
                props["weight"] = Pango.Weight.BOLD
            if spec.get("italic"):
                props["style"] = Pango.Style.ITALIC
            if spec.get("underline"):
                props["underline"] = Pango.Underline.SINGLE
            return self.buffer.create_tag(name, **props)

        for name, spec in rules.TAG_SPECS.items():
            ensure(name, spec)

    def set_code_font(self, font_desc_str):
        """Set the font used for inline/fenced code (Pango font-desc string)."""
        self._code_font = font_desc_str
        table = self.buffer.get_tag_table()
        for name in rules.CODE_TAG_NAMES:
            tag = table.lookup(name)
            if tag is not None:
                tag.set_property("font", font_desc_str)

    def highlight(self):
        buf = self.buffer
        start = buf.get_start_iter()
        end = buf.get_end_iter()
        for name in rules.ALL_TAG_NAMES:
            buf.remove_tag_by_name(name, start, end)
        text = buf.get_text(start, end, True)
        for tag_name, s_off, e_off in rules.iter_spans(text):
            s = buf.get_iter_at_offset(s_off)
            e = buf.get_iter_at_offset(e_off)
            buf.apply_tag_by_name(tag_name, s, e)
