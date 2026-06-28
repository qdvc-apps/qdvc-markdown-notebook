"""
editortab.py — a single editor tab for QDVC Markdown Notebook.

Each EditorTab owns its own Gtk.TextView, buffer, highlighter, and the note (if
any) currently open in it, plus the per-tab dirty/loading flags that used to
live directly on the window. The window holds a Gtk.Notebook of these.

The tab label is a small horizontal box with a title and a close button, in the
style of Caja / typical GTK file managers.
"""

import os

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango, GLib  # noqa: E402

from . import model
from . import pango_markdown
from .highlighter import MarkdownHighlighter

UNTITLED_LABEL = "Untitled"
MAX_TAB_TITLE = 12  # characters before truncation with an ellipsis


class EditorTab:
    """
    One tab in the editor notebook.

    Public attributes:
        widget      the page widget added to the Gtk.Notebook (a ScrolledWindow)
        tab_label   the widget shown on the tab (title + close button)
        text_view   the Gtk.TextView
        note        the model.Note open here, or None for an empty tab
        dirty       True if there are unsaved edits
    """

    def __init__(self, on_changed, on_close, code_font="monospace 11"):
        """
        on_changed(tab): called when this tab's buffer changes (not during
                         programmatic loads).
        on_close(tab):   called when the tab's close button is clicked.
        code_font:       Pango font-description string for code spans/blocks.
        """
        self._on_changed = on_changed
        self._on_close = on_close

        self.note = None
        self.dirty = False
        self._loading = False
        self.preview = False  # whether this tab is showing rendered markdown
        self._code_font = code_font     # used when rendering preview code spans
        self._preview_font = None       # body font for the preview view

        # ---- editor widget ----
        # The page widget is a Gtk.Stack with children: the editor (a scrolled
        # TextView), a read-only rendered-markdown preview, and a placeholder
        # shown when no note is loaded.
        self.widget = Gtk.Stack()

        editor_scroll = Gtk.ScrolledWindow()
        editor_scroll.set_policy(Gtk.PolicyType.AUTOMATIC,
                                 Gtk.PolicyType.AUTOMATIC)

        self.text_buffer = Gtk.TextBuffer()
        self.text_view = Gtk.TextView(buffer=self.text_buffer)
        self.text_view.set_monospace(True)
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.text_view.set_left_margin(8)
        self.text_view.set_right_margin(8)
        self.text_view.set_top_margin(8)
        self.text_view.set_bottom_margin(8)

        self.highlighter = MarkdownHighlighter(self.text_buffer,
                                               code_font=code_font)
        # A dedicated tag for search-term highlighting (yellow background).
        self._search_tag = self.text_buffer.create_tag(
            "search_match", background="#fff176")
        self._search_highlight = None
        self.text_buffer.connect("changed", self._buffer_changed)

        editor_scroll.add(self.text_view)
        self.widget.add_named(editor_scroll, "editor")

        # ---- rendered-markdown preview (read-only) ----
        preview_scroll = Gtk.ScrolledWindow()
        preview_scroll.set_policy(Gtk.PolicyType.AUTOMATIC,
                                  Gtk.PolicyType.AUTOMATIC)
        self.preview_buffer = Gtk.TextBuffer()
        self.preview_view = Gtk.TextView(buffer=self.preview_buffer)
        self.preview_view.set_editable(False)
        self.preview_view.set_cursor_visible(False)
        self.preview_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.preview_view.set_left_margin(8)
        self.preview_view.set_right_margin(8)
        self.preview_view.set_top_margin(8)
        self.preview_view.set_bottom_margin(8)
        preview_scroll.add(self.preview_view)
        self.widget.add_named(preview_scroll, "preview")

        self.widget.add_named(self._build_placeholder(), "placeholder")
        self.widget.set_visible_child_name("placeholder")
        self.widget.show_all()

        # ---- tab label (title + close button) ----
        self.tab_label = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                                 spacing=4)
        self._title_label = Gtk.Label(label=UNTITLED_LABEL)

        close_btn = Gtk.Button()
        close_btn.set_relief(Gtk.ReliefStyle.NONE)
        close_btn.set_focus_on_click(False)
        close_btn.add(Gtk.Image.new_from_icon_name(
            "window-close", Gtk.IconSize.MENU))
        close_btn.set_tooltip_text("Close tab")
        close_btn.connect("clicked", lambda _b: self._on_close(self))

        self.tab_label.pack_start(self._title_label, True, True, 0)
        self.tab_label.pack_start(close_btn, False, False, 0)
        self.tab_label.show_all()

        self._refresh_title()
        self._update_view_mode()

    # --------------------------------------------------- placeholder ----- #
    def _build_placeholder(self):
        """A centred, dim message shown when the tab has no note open."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_valign(Gtk.Align.CENTER)
        box.set_halign(Gtk.Align.CENTER)
        label = Gtk.Label()
        label.set_markup(
            "<span size='large' foreground='#888888'>"
            "Select a note to start reading or editing</span>")
        box.add(label)
        return box

    def _update_view_mode(self):
        """Choose which stack child to show based on note/preview state."""
        if not self.note:
            self.widget.set_visible_child_name("placeholder")
        elif self.preview:
            self.widget.set_visible_child_name("preview")
        else:
            self.widget.set_visible_child_name("editor")

    def set_preview(self, on):
        """
        Turn rendered-markdown preview on/off for this tab. When turning on, the
        preview is (re)rendered from the current editor content.
        """
        self.preview = bool(on)
        if self.preview:
            self._render_preview()
        self._update_view_mode()

    def _render_preview(self):
        """Render the current editor content to the read-only preview buffer."""
        markup = pango_markdown.render(self.get_content(),
                                       code_font=self._code_font)
        self.preview_buffer.set_text("")
        start = self.preview_buffer.get_start_iter()
        try:
            self.preview_buffer.insert_markup(start, markup, -1)
        except (TypeError, GLib.GError):  # pragma: no cover
            # Extremely defensive: if markup somehow fails, fall back to plain.
            self.preview_buffer.set_text(self.get_content())

    # --------------------------------------------------------------- API -- #
    def apply_font(self, font_desc_str):
        self.text_view.override_font(Pango.FontDescription(font_desc_str))

    def apply_code_font(self, font_desc_str):
        self._code_font = font_desc_str
        self.highlighter.set_code_font(font_desc_str)
        if self.preview:
            self._render_preview()

    def apply_preview_font(self, font_desc_str):
        """Body font for the rendered-markdown preview (code uses code_font)."""
        self._preview_font = font_desc_str
        self.preview_view.override_font(Pango.FontDescription(font_desc_str))

    def apply_editor_line_spacing(self, pixels):
        self.text_view.set_pixels_below_lines(int(pixels))
        self.text_view.set_pixels_inside_wrap(int(pixels))

    def apply_preview_line_spacing(self, pixels):
        self.preview_view.set_pixels_below_lines(int(pixels))
        self.preview_view.set_pixels_inside_wrap(int(pixels))

    def set_editable(self, editable):
        """Toggle whether the user can modify this tab's text (read-only mode)."""
        self.text_view.set_editable(editable)
        self.text_view.set_cursor_visible(editable)

    def highlight_search(self, query):
        """
        Highlight every (case-insensitive) occurrence of `query` in this tab's
        editor text with a yellow background. A blank/None query clears any
        existing highlight. Also re-applied after content (re)loads.
        """
        self._search_highlight = query or None
        self._apply_search_highlight()

    def _apply_search_highlight(self):
        buf = self.text_buffer
        start, end = buf.get_bounds()
        buf.remove_tag(self._search_tag, start, end)
        query = getattr(self, "_search_highlight", None)
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

    def get_content(self):
        start = self.text_buffer.get_start_iter()
        end = self.text_buffer.get_end_iter()
        return self.text_buffer.get_text(start, end, True)

    def clear(self):
        """Reset to an empty, note-less tab."""
        self._loading = True
        self.text_buffer.set_text("")
        self._loading = False
        self.note = None
        self.dirty = False
        self._refresh_title()
        self._update_view_mode()

    def load_note(self, note):
        """
        Load `note` into this tab. Returns True on success, False on read error
        (the caller is responsible for showing the error).
        """
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
        self._refresh_title()
        self._update_view_mode()
        return True

    def save(self):
        """
        Write this tab's content to its note. Returns True on success, False if
        there is no note or the write failed (caller shows the error).
        """
        if not self.note:
            return False
        try:
            model.write_note(self.note, self.get_content())
        except OSError:
            return False
        self.dirty = False
        self._refresh_title()
        return True

    def title_text(self):
        if self.note:
            return self.note.display_name()
        return UNTITLED_LABEL

    # --------------------------------------------------------- internal -- #
    def _buffer_changed(self, _buffer):
        if self._loading:
            return
        self.dirty = True
        self.highlighter.highlight()
        self._apply_search_highlight()
        self._refresh_title()
        self._on_changed(self)

    def _refresh_title(self):
        title = self.title_text()
        if len(title) > MAX_TAB_TITLE:
            title = title[:MAX_TAB_TITLE] + "\u2026"
        if self.dirty:
            title = "*" + title
        self._title_label.set_text(title)
        self._title_label.set_tooltip_text(
            self.note.path if self.note else "Unsaved note")
