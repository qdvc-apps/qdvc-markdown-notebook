"""
gtk3_editortab.py — a single editor tab for QDVC Markdown Notebook (GTK3).

Each EditorTab owns its own Gtk.TextView, buffer, highlighter, and the note (if
any) currently open in it, plus the per-tab dirty/loading flags that used to
live directly on the window. The window holds a Gtk.Notebook of these.

The tab label is a small horizontal box with a title and a close button, in the
style of Caja / typical GTK file managers.

User-facing text comes from qdvcmdnb_lib.strings (Editor namespace).
"""

import os

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango, GLib  # noqa: E402

from . import model
from . import pango_markdown
from .gtk3_highlighter import MarkdownHighlighter
from .strings import Editor as S

# Backwards-compatible alias: this used to be a module constant. It now points
# at the centralised string so existing references keep working.
UNTITLED_LABEL = S.UNTITLED
MAX_TAB_TITLE = 12  # default characters before truncation (configurable in
                    # Preferences; the window passes the user's choice in)
TAB_SPACES = 4      # spaces a Tab key expands to in edit mode


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

    def __init__(self, on_changed, on_close, code_font="monospace 11",
                 tab_title_length=MAX_TAB_TITLE, on_context_menu=None):
        """
        on_changed(tab): called when this tab's buffer changes (not during
                         programmatic loads).
        on_close(tab):   called when the tab's close button is clicked.
        code_font:       Pango font-description string for code spans/blocks.
        tab_title_length: characters of the title shown before truncation.
        on_context_menu(tab, event): called on a right-click of the tab label
                         (None disables it). The window uses it to show the same
                         context menu as a pane-2 right-click, plus "Locate in
                         subfolders".
        """
        self._on_changed = on_changed
        self._on_close = on_close
        self._tab_title_length = int(tab_title_length)
        self._on_context_menu = on_context_menu

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
        # Convert a Tab key press in edit mode to TAB_SPACES spaces.
        self.text_view.connect("key-press-event", self._on_textview_key_press)

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
        # The title sits in an EventBox so it can receive button-press events
        # (a plain Gtk.Box/Label has no input window). Right-clicking it raises
        # the tab context menu via the on_context_menu callback.
        self._title_event_box = Gtk.EventBox()
        self._title_event_box.set_visible_window(False)
        self._title_event_box.add(self._title_label)
        self._title_event_box.connect("button-press-event",
                                      self._on_tab_label_button_press)

        close_btn = Gtk.Button()
        close_btn.set_relief(Gtk.ReliefStyle.NONE)
        close_btn.set_focus_on_click(False)
        close_btn.add(Gtk.Image.new_from_icon_name(
            "window-close", Gtk.IconSize.MENU))
        close_btn.set_tooltip_text(S.CLOSE_TAB_TIP)
        close_btn.connect("clicked", lambda _b: self._on_close(self))

        self.tab_label.pack_start(self._title_event_box, True, True, 0)
        self.tab_label.pack_start(close_btn, False, False, 0)
        self.tab_label.show_all()

        self._refresh_title()
        self._update_view_mode()

    def _on_tab_label_button_press(self, _widget, event):
        """Right-click on the tab title → tab context menu (if a callback is
        set and this tab has a note open)."""
        if event.button != 3:
            return False
        if self._on_context_menu is None or self.note is None:
            return False
        self._on_context_menu(self, event)
        return True

    # --------------------------------------------------- placeholder ----- #
    def _build_placeholder(self):
        """A centred, dim message shown when the tab has no note open."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_valign(Gtk.Align.CENTER)
        box.set_halign(Gtk.Align.CENTER)
        label = Gtk.Label()
        label.set_markup(
            f"<span size='large' foreground='#888888'>"
            f"{S.EMPTY_PLACEHOLDER}</span>")
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
    def _on_textview_key_press(self, _view, event):
        """
        Expand a Tab keypress to TAB_SPACES spaces while editing. Returns True
        to swallow the original Tab so focus doesn't jump out of the editor.
        Shift+Tab and read-only mode are left to the default handler.
        """
        from gi.repository import Gdk
        if event.keyval != Gdk.KEY_Tab:
            return False
        if event.state & Gdk.ModifierType.SHIFT_MASK:
            return False
        if not self.text_view.get_editable():
            return False
        self.text_buffer.insert_at_cursor(" " * TAB_SPACES)
        return True

    def set_tab_title_length(self, length):
        """Set the character budget for the tab title and refresh it."""
        self._tab_title_length = max(1, int(length))
        self._refresh_title()

    def apply_font(self, font_desc_str):
        # Set the editor body font. override_font takes a Pango.FontDescription
        # parsed from a string like "monospace 11".
        self.text_view.override_font(Pango.FontDescription(font_desc_str))

    def apply_code_font(self, font_desc_str):
        # Change the font used for code spans/blocks. The highlighter applies it
        # to the editor's code tags; if previewing, re-render so the preview
        # picks it up too.
        self._code_font = font_desc_str
        self.highlighter.set_code_font(font_desc_str)
        if self.preview:
            self._render_preview()

    def apply_preview_font(self, font_desc_str):
        """Body font for the rendered-markdown preview (code uses code_font).
        Stored so a later re-render keeps it; override_font sets it now."""
        self._preview_font = font_desc_str
        self.preview_view.override_font(Pango.FontDescription(font_desc_str))

    def apply_editor_line_spacing(self, pixels):
        # Extra vertical space in the editor: set_pixels_below_lines adds space
        # after each paragraph; set_pixels_inside_wrap adds it between the
        # wrapped rows of one long line.
        self.text_view.set_pixels_below_lines(int(pixels))
        self.text_view.set_pixels_inside_wrap(int(pixels))

    def apply_preview_line_spacing(self, pixels):
        # Same two spacing knobs, applied to the preview view.
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
        # Re-tag the buffer for the stored search term. A Gtk.TextBuffer marks up
        # ranges with "tags"; we first remove our search tag from the whole
        # buffer (get_bounds gives start/end iters), then walk the lowercased
        # text with str.find and apply_tag over each match. get_iter_at_offset
        # converts a character offset into a TextIter (a position handle).
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
        # Return the editor's full text. A TextBuffer is addressed by iters;
        # get_text(start, end, include_hidden) returns the string between them.
        start = self.text_buffer.get_start_iter()
        end = self.text_buffer.get_end_iter()
        return self.text_buffer.get_text(start, end, True)

    def scroll_to_line(self, line_index):
        """
        Move the cursor to the start of `line_index` (0-based) and scroll it into
        view. Used by the outline pane to jump to a heading. In preview mode the
        editor is hidden, so this scrolls the preview view to the same line
        instead (best-effort: preview line numbers may differ from source, so we
        clamp). Out-of-range indices are clamped to the buffer.
        """
        n_lines = self.text_buffer.get_line_count()
        line = max(0, min(int(line_index), max(0, n_lines - 1)))
        it = self.text_buffer.get_iter_at_line(line)
        self.text_buffer.place_cursor(it)
        # scroll_to_iter needs the view realized; use within_margin for a little
        # context above the target line.
        self.text_view.scroll_to_iter(it, 0.1, True, 0.0, 0.0)
        if not self.preview:
            self.text_view.grab_focus()

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
        # The untruncated tab title: the note's display name, or the "Untitled"
        # placeholder for an empty tab. (No GTK here.)
        if self.note:
            return self.note.display_name()
        return UNTITLED_LABEL

    # --------------------------------------------------------- internal -- #
    def _buffer_changed(self, _buffer):
        # The TextBuffer's "changed" signal handler: fires on every edit. We
        # ignore changes made during a programmatic load (_loading guard);
        # otherwise mark the tab dirty, re-run highlighting/search tagging,
        # refresh the title (to show the * marker), and notify the window.
        if self._loading:
            return
        self.dirty = True
        self.highlighter.highlight()
        self._apply_search_highlight()
        self._refresh_title()
        self._on_changed(self)

    def _refresh_title(self):
        # Recompute the tab label: truncate the title past the configured limit
        # (adding an ellipsis), prefix "*" when dirty, and set the label text +
        # a tooltip showing the full file path (or a placeholder when unsaved).
        title = self.title_text()
        limit = getattr(self, "_tab_title_length", MAX_TAB_TITLE)
        if len(title) > limit:
            title = title[:limit] + "\u2026"
        if self.dirty:
            title = "*" + title
        self._title_label.set_text(title)
        self._title_label.set_tooltip_text(
            self.note.path if self.note else S.UNSAVED_TOOLTIP)
