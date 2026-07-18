"""
gtk4_editorview.py — one editor "tab" for the GTK 4 front-end.

The GTK 4 analogue of qdvc/gtk3/gtk3_editortab.EditorTab. It owns a Gtk.TextView
+ buffer + highlighter, an optional rendered-markdown preview, a placeholder for
the empty state, and per-tab dirty / read-only / preview flags — exactly the
same model state as the GTK 3 tab, reusing the same pure core (``model``,
``pango_markdown``) unchanged.

Differences from GTK 3 (recorded in docs/MAINTENANCE_GTK3_GTK4.md):
  * The page widget is a Gtk.Stack with "editor"/"preview"/"placeholder"
    children (same idea as GTK 3), but children are added with
    ``add_named`` and set with ``set_visible_child_name`` (GTK 4 keeps these).
  * Tabs are hosted by an ``Adw.TabView`` in the window, not a Gtk.Notebook, so
    the per-tab label/close button is provided by ``Adw.TabPage`` rather than a
    hand-built label box. This view therefore exposes ``title_text()`` and the
    dirty flag and lets the window drive the Adw.TabPage title.
  * Fonts are applied via CSS (GTK 4 removed ``override_font``); the window owns
    a ``Gtk.CssProvider`` and this view exposes the CSS class names it uses.
"""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Pango, GLib  # noqa: E402

from .. import model
from .. import pango_markdown
from .gtk4_highlighter import MarkdownHighlighter
from ..strings import Editor as S

UNTITLED_LABEL = S.UNTITLED
TAB_SPACES = 4


class EditorView:
    """One editor page for the GTK 4 Adw.TabView (see module docstring)."""

    def __init__(self, on_changed, code_font="monospace 11"):
        self._on_changed = on_changed
        self._code_font = code_font

        self.note = None
        self.dirty = False
        self._loading = False
        self.preview = False
        self.read_only = True
        self._search_highlight = None

        # Page widget: a Gtk.Stack (editor / preview / placeholder).
        self.widget = Gtk.Stack()

        editor_scroll = Gtk.ScrolledWindow()
        editor_scroll.set_policy(Gtk.PolicyType.AUTOMATIC,
                                 Gtk.PolicyType.AUTOMATIC)
        editor_scroll.set_hexpand(True)
        editor_scroll.set_vexpand(True)
        self.text_buffer = Gtk.TextBuffer()
        self.text_view = Gtk.TextView.new_with_buffer(self.text_buffer)
        self.text_view.set_monospace(True)
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.text_view.set_left_margin(8)
        self.text_view.set_right_margin(8)
        self.text_view.set_top_margin(8)
        self.text_view.set_bottom_margin(8)
        self.text_view.add_css_class("qdvc-editor")

        self.highlighter = MarkdownHighlighter(self.text_buffer,
                                               code_font=code_font)
        self._search_tag = self.text_buffer.create_tag(
            "search_match", background="#fff176")
        self.text_buffer.connect("changed", self._buffer_changed)

        # Tab → spaces via a key controller (GTK 4 uses event controllers).
        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self._on_key_pressed)
        self.text_view.add_controller(key)

        editor_scroll.set_child(self.text_view)
        self.widget.add_named(editor_scroll, "editor")

        # Rendered-markdown preview (read-only).
        preview_scroll = Gtk.ScrolledWindow()
        preview_scroll.set_policy(Gtk.PolicyType.AUTOMATIC,
                                  Gtk.PolicyType.AUTOMATIC)
        self.preview_buffer = Gtk.TextBuffer()
        self.preview_view = Gtk.TextView.new_with_buffer(self.preview_buffer)
        self.preview_view.set_editable(False)
        self.preview_view.set_cursor_visible(False)
        self.preview_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.preview_view.set_left_margin(8)
        self.preview_view.set_right_margin(8)
        self.preview_view.set_top_margin(8)
        self.preview_view.set_bottom_margin(8)
        self.preview_view.add_css_class("qdvc-preview")
        preview_scroll.set_child(self.preview_view)
        self.widget.add_named(preview_scroll, "preview")

        placeholder = Gtk.Label(label=S.EMPTY_PLACEHOLDER)
        placeholder.add_css_class("dim-label")
        placeholder.set_valign(Gtk.Align.CENTER)
        placeholder.set_halign(Gtk.Align.CENTER)
        self.widget.add_named(placeholder, "placeholder")

        self._update_view_mode()

    # ------------------------------------------------------------ view -- #
    def _update_view_mode(self):
        if not self.note:
            self.widget.set_visible_child_name("placeholder")
        elif self.preview:
            self.widget.set_visible_child_name("preview")
        else:
            self.widget.set_visible_child_name("editor")

    def set_read_only(self, on):
        self.read_only = bool(on)
        self.text_view.set_editable(not self.read_only)
        self.text_view.set_cursor_visible(not self.read_only)

    def set_preview(self, on):
        self.preview = bool(on)
        if self.preview:
            self._render_preview()
        self._update_view_mode()

    def _render_preview(self):
        markup = pango_markdown.render(self.get_content(),
                                       code_font=self._code_font)
        self.preview_buffer.set_text("")
        start = self.preview_buffer.get_start_iter()
        try:
            self.preview_buffer.insert_markup(start, markup, -1)
        except (TypeError, GLib.GError):  # pragma: no cover
            self.preview_buffer.set_text(self.get_content())

    # ------------------------------------------------------------ data -- #
    def get_content(self):
        start = self.text_buffer.get_start_iter()
        end = self.text_buffer.get_end_iter()
        return self.text_buffer.get_text(start, end, True)

    def clear(self):
        self._loading = True
        self.text_buffer.set_text("")
        self._loading = False
        self.note = None
        self.dirty = False
        self._update_view_mode()

    def load_note(self, note):
        try:
            content = model.read_note(note)
        except (OSError, UnicodeDecodeError):
            return False
        self._loading = True
        self.text_buffer.set_text(content)
        self._loading = False
        self.note = note
        self.dirty = False
        self.highlighter.highlight()
        self._apply_search_highlight()
        if self.preview:
            self._render_preview()
        self._update_view_mode()
        return True

    def save(self):
        if not self.note:
            return False
        try:
            model.write_note(self.note, self.get_content())
        except OSError:
            return False
        self.dirty = False
        return True

    def title_text(self):
        if self.note:
            return self.note.display_name()
        return UNTITLED_LABEL

    def scroll_to_line(self, line_index):
        n_lines = self.text_buffer.get_line_count()
        line = max(0, min(int(line_index), max(0, n_lines - 1)))
        it = self.text_buffer.get_iter_at_line(line)
        # GTK4 get_iter_at_line returns (found, iter).
        if isinstance(it, tuple):
            it = it[1]
        self.text_buffer.place_cursor(it)
        self.text_view.scroll_to_iter(it, 0.1, True, 0.0, 0.0)
        if not self.preview:
            self.text_view.grab_focus()

    # -------------------------------------------------------- search -- #
    def highlight_search(self, query):
        self._search_highlight = query or None
        self._apply_search_highlight()

    def _apply_search_highlight(self):
        buf = self.text_buffer
        start, end = buf.get_bounds()
        buf.remove_tag(self._search_tag, start, end)
        query = self._search_highlight
        if not query:
            return
        hay = self.get_content().lower()
        needle = query.lower()
        if not needle:
            return
        idx = hay.find(needle)
        while idx != -1:
            s = buf.get_iter_at_offset(idx)
            e = buf.get_iter_at_offset(idx + len(needle))
            buf.apply_tag(self._search_tag, s, e)
            idx = hay.find(needle, idx + len(needle))

    # ------------------------------------------------------- fonts -- #
    def apply_code_font(self, font_desc_str):
        self._code_font = font_desc_str
        self.highlighter.set_code_font(font_desc_str)
        if self.preview:
            self._render_preview()

    # ---------------------------------------------------- internal -- #
    def _buffer_changed(self, _buffer):
        if self._loading:
            return
        self.dirty = True
        self.highlighter.highlight()
        self._apply_search_highlight()
        self._on_changed(self)

    def _on_key_pressed(self, _controller, keyval, _keycode, state):
        from gi.repository import Gdk
        if keyval != Gdk.KEY_Tab:
            return False
        if state & Gdk.ModifierType.SHIFT_MASK:
            return False
        if not self.text_view.get_editable():
            return False
        self.text_buffer.insert_at_cursor(" " * TAB_SPACES, -1)
        return True
