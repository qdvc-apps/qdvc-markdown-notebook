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
from gi.repository import Gtk, Pango  # noqa: E402

from . import model
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

        # ---- editor widget ----
        # The page widget is a Gtk.Stack with two children: the editor (a
        # scrolled TextView) and a placeholder shown when no note is loaded.
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
        self.text_buffer.connect("changed", self._buffer_changed)

        editor_scroll.add(self.text_view)
        self.widget.add_named(editor_scroll, "editor")
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
        """Show the editor when a note is open, else the placeholder."""
        name = "editor" if self.note else "placeholder"
        self.widget.set_visible_child_name(name)

    # --------------------------------------------------------------- API -- #
    def apply_font(self, font_desc_str):
        self.text_view.override_font(Pango.FontDescription(font_desc_str))

    def apply_code_font(self, font_desc_str):
        self.highlighter.set_code_font(font_desc_str)

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
