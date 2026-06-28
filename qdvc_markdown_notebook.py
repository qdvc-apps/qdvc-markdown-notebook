#!/usr/bin/env python3
"""
qdvc_markdown_notebook.py

A three-pane markdown notebook viewer/editor for the MATE / GNOME2-era
desktop, built with GTK 3 via PyGObject.

Usage:
    python3 qdvc_markdown_notebook.py /path/to/markdown/data
    python3 qdvc_markdown_notebook.py        # start empty, open folder via Ctrl+O

See MAINTENANCE.md for architecture and maintenance notes.
"""

import os
import sys
import re
import time

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango, GLib, Gio  # noqa: E402


APP_NAME = "QDVC Markdown Notebook"
MARKDOWN_EXTENSIONS = (".md", ".markdown", ".mdown", ".mkd", ".txt")

# Sort modes
SORT_ALPHA = "alpha"
SORT_DATE_NEW = "date_new"
SORT_DATE_OLD = "date_old"

# Special sentinel for the "All Notes" virtual folder.
ALL_NOTES = object()


# --------------------------------------------------------------------------- #
# Markdown syntax highlighting (lightweight, regex-based, monospace only)
# --------------------------------------------------------------------------- #
class MarkdownHighlighter:
    """
    Applies syntax-highlighting tags to a Gtk.TextBuffer.

    Deliberately simple and line-oriented. No external markdown library is
    used: the requirement is a monospace view with *no font-size variation*,
    just colour/weight cues. Re-highlighting is done on the whole buffer,
    which is fine for typical note sizes.
    """

    def __init__(self, buffer):
        self.buffer = buffer
        self._make_tags()

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
        ensure("code_inline", foreground="#ce5c00",
               family="monospace", background="#f0f0f0")
        ensure("code_block", foreground="#4e9a06",
               family="monospace", background="#f5f5f5")
        ensure("bold", weight=Pango.Weight.BOLD)
        ensure("italic", style=Pango.Style.ITALIC)
        ensure("link", foreground="#3465a4", underline=Pango.Underline.SINGLE)

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


# --------------------------------------------------------------------------- #
# Data model helpers
# --------------------------------------------------------------------------- #
class Note:
    """A single markdown file on disk."""

    __slots__ = ("path", "name", "mtime")

    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        try:
            self.mtime = os.path.getmtime(path)
        except OSError:
            self.mtime = 0.0

    def display_name(self):
        base = self.name
        for ext in MARKDOWN_EXTENSIONS:
            if base.lower().endswith(ext):
                return base[: -len(ext)]
        return base


def is_markdown(filename):
    return filename.lower().endswith(MARKDOWN_EXTENSIONS)


def collect_notes(folder):
    """
    Return a list of Note objects for all markdown files at any depth under
    `folder`. Used for "All Notes" and for an aggregated subfolder view.
    """
    notes = []
    for root, _dirs, files in os.walk(folder):
        for f in files:
            if is_markdown(f):
                notes.append(Note(os.path.join(root, f)))
    return notes


def immediate_subfolders(root):
    """Return sorted list of immediate subfolder names of `root`."""
    try:
        entries = os.listdir(root)
    except OSError:
        return []
    subs = [
        e for e in entries
        if os.path.isdir(os.path.join(root, e)) and not e.startswith(".")
    ]
    return sorted(subs, key=str.lower)


# --------------------------------------------------------------------------- #
# Main window
# --------------------------------------------------------------------------- #
class NotebookWindow(Gtk.Window):

    def __init__(self, root_folder=None):
        super().__init__(title=APP_NAME)
        self.set_default_size(1000, 640)

        self.root_folder = None
        self.current_note = None          # Note currently open in editor
        self.current_subfolder = ALL_NOTES
        self.sort_mode = SORT_ALPHA
        self._dirty = False
        self._loading = False             # guard against spurious "changed"

        self._build_ui()

        if root_folder:
            self.open_folder(os.path.abspath(root_folder))

        self.connect("destroy", Gtk.main_quit)
        self.connect("delete-event", self._on_delete_event)

    # ----------------------------------------------------------------- UI -- #
    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(vbox)

        vbox.pack_start(self._build_menubar(), False, False, 0)
        vbox.pack_start(self._build_toolbar(), False, False, 0)

        # Three-pane layout via nested GtkPaned.
        outer = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        inner = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)

        outer.pack1(self._build_sidebar(), resize=False, shrink=False)
        outer.pack2(inner, resize=True, shrink=False)
        inner.pack1(self._build_notelist(), resize=False, shrink=False)
        inner.pack2(self._build_editor(), resize=True, shrink=False)

        outer.set_position(200)
        inner.set_position(280)

        vbox.pack_start(outer, True, True, 0)
        vbox.pack_start(self._build_statusbar(), False, False, 0)

    def _build_menubar(self):
        menubar = Gtk.MenuBar()
        accel = Gtk.AccelGroup()
        self.add_accel_group(accel)

        # ---- File menu ----
        file_menu = Gtk.Menu()
        file_item = Gtk.MenuItem(label="File")
        file_item.set_submenu(file_menu)

        mi_new = Gtk.MenuItem(label="New")
        mi_new.add_accelerator("activate", accel, Gdk.KEY_n,
                               Gdk.ModifierType.CONTROL_MASK,
                               Gtk.AccelFlags.VISIBLE)
        mi_new.connect("activate", self.on_new_note)
        file_menu.append(mi_new)

        mi_save = Gtk.MenuItem(label="Save")
        mi_save.add_accelerator("activate", accel, Gdk.KEY_s,
                                Gdk.ModifierType.CONTROL_MASK,
                                Gtk.AccelFlags.VISIBLE)
        mi_save.connect("activate", self.on_save_note)
        file_menu.append(mi_save)

        mi_open = Gtk.MenuItem(label="Open Working Folder")
        mi_open.add_accelerator("activate", accel, Gdk.KEY_o,
                                Gdk.ModifierType.CONTROL_MASK,
                                Gtk.AccelFlags.VISIBLE)
        mi_open.connect("activate", self.on_open_folder)
        file_menu.append(mi_open)

        file_menu.append(Gtk.SeparatorMenuItem())

        mi_quit = Gtk.MenuItem(label="Quit")
        # Note: the spec listed Ctrl+S for Quit; that collides with Save,
        # so Quit is bound to the conventional Ctrl+Q instead. See MAINTENANCE.md.
        mi_quit.add_accelerator("activate", accel, Gdk.KEY_q,
                                Gdk.ModifierType.CONTROL_MASK,
                                Gtk.AccelFlags.VISIBLE)
        mi_quit.connect("activate", self.on_quit)
        file_menu.append(mi_quit)

        menubar.append(file_item)

        # ---- View menu ----
        view_menu = Gtk.Menu()
        view_item = Gtk.MenuItem(label="View")
        view_item.set_submenu(view_menu)

        group = []
        mi_alpha = Gtk.RadioMenuItem(label="Sort: Alphabetical", group=None)
        group = mi_alpha.get_group()
        mi_alpha.set_active(True)
        mi_alpha.connect("toggled", self.on_sort_changed, SORT_ALPHA)
        view_menu.append(mi_alpha)

        mi_new_first = Gtk.RadioMenuItem(label="Sort: Date, newest first",
                                         group=mi_alpha)
        mi_new_first.connect("toggled", self.on_sort_changed, SORT_DATE_NEW)
        view_menu.append(mi_new_first)

        mi_old_first = Gtk.RadioMenuItem(label="Sort: Date, oldest first",
                                         group=mi_alpha)
        mi_old_first.connect("toggled", self.on_sort_changed, SORT_DATE_OLD)
        view_menu.append(mi_old_first)

        menubar.append(view_item)
        return menubar

    def _build_toolbar(self):
        toolbar = Gtk.Toolbar()
        toolbar.set_style(Gtk.ToolbarStyle.BOTH)

        btn_new = Gtk.ToolButton(icon_name="document-new")
        btn_new.set_label("New note")
        btn_new.set_tooltip_text("Create a new note in the selected folder")
        btn_new.connect("clicked", self.on_new_note)
        toolbar.insert(btn_new, -1)

        btn_save = Gtk.ToolButton(icon_name="document-save")
        btn_save.set_label("Save note")
        btn_save.set_tooltip_text("Save the current note")
        btn_save.connect("clicked", self.on_save_note)
        toolbar.insert(btn_save, -1)

        return toolbar

    def _build_sidebar(self):
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        # Columns: display label (str), folder name or "" for All Notes (str),
        #          is_all_notes (bool)
        self.sidebar_store = Gtk.TreeStore(str, str, bool)
        self.sidebar_view = Gtk.TreeView(model=self.sidebar_store)
        self.sidebar_view.set_headers_visible(False)

        renderer = Gtk.CellRendererText()
        col = Gtk.TreeViewColumn("Folders", renderer, text=0)
        self.sidebar_view.append_column(col)

        self.sidebar_view.get_selection().connect(
            "changed", self.on_sidebar_selection_changed)

        scroll.add(self.sidebar_view)
        return scroll

    def _build_notelist(self):
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        # Columns: display name (str), full path (str), mtime (float)
        self.note_store = Gtk.ListStore(str, str, float)
        self.note_view = Gtk.TreeView(model=self.note_store)
        self.note_view.set_headers_visible(False)

        renderer = Gtk.CellRendererText()
        renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
        col = Gtk.TreeViewColumn("Notes", renderer, text=0)
        self.note_view.append_column(col)

        self.note_view.get_selection().connect(
            "changed", self.on_note_selection_changed)

        scroll.add(self.note_view)
        return scroll

    def _build_editor(self):
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self.text_buffer = Gtk.TextBuffer()
        self.text_view = Gtk.TextView(buffer=self.text_buffer)
        self.text_view.set_monospace(True)
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.text_view.set_left_margin(8)
        self.text_view.set_right_margin(8)
        self.text_view.set_top_margin(8)
        self.text_view.set_bottom_margin(8)

        # Force a single uniform monospace size, no scaling whatsoever.
        font = Pango.FontDescription("monospace 11")
        self.text_view.override_font(font)

        self.highlighter = MarkdownHighlighter(self.text_buffer)
        self.text_buffer.connect("changed", self.on_text_changed)

        scroll.add(self.text_view)
        return scroll

    def _build_statusbar(self):
        self.statusbar = Gtk.Statusbar()
        self._status_ctx = self.statusbar.get_context_id("main")
        return self.statusbar

    # -------------------------------------------------------- status bar -- #
    def update_status(self):
        count = len(self.note_store)
        if self.current_note:
            sel = self.current_note.display_name()
        else:
            sel = "none"
        msg = f"{count} item(s)  |  Selected: {sel}"
        if self._dirty:
            msg += "  *"
        self.statusbar.pop(self._status_ctx)
        self.statusbar.push(self._status_ctx, msg)

    # ------------------------------------------------------ folder logic -- #
    def open_folder(self, folder):
        if not folder or not os.path.isdir(folder):
            self._error_dialog(f"Not a folder:\n{folder}")
            return
        self.root_folder = folder
        self.set_title(f"{APP_NAME} \u2014 {folder}")
        self.current_subfolder = ALL_NOTES
        self.current_note = None
        self._reload_sidebar()
        self._reload_notelist()
        self._clear_editor()
        self.update_status()

    def _reload_sidebar(self):
        self.sidebar_store.clear()
        # Top segment: "All Notes".
        self.sidebar_store.append(None, ["All Notes", "", True])
        # Bottom segment: immediate subfolders.
        if self.root_folder:
            for sub in immediate_subfolders(self.root_folder):
                self.sidebar_store.append(None, [sub, sub, False])
        # Select "All Notes" by default.
        self.sidebar_view.get_selection().select_path(Gtk.TreePath.new_first())

    def _notes_for_current_subfolder(self):
        if not self.root_folder:
            return []
        if self.current_subfolder is ALL_NOTES:
            return collect_notes(self.root_folder)
        folder = os.path.join(self.root_folder, self.current_subfolder)
        return collect_notes(folder)

    def _sorted_notes(self, notes):
        if self.sort_mode == SORT_ALPHA:
            return sorted(notes, key=lambda n: n.display_name().lower())
        if self.sort_mode == SORT_DATE_NEW:
            return sorted(notes, key=lambda n: n.mtime, reverse=True)
        if self.sort_mode == SORT_DATE_OLD:
            return sorted(notes, key=lambda n: n.mtime)
        return notes

    def _reload_notelist(self, select_path=None):
        self.note_store.clear()
        notes = self._sorted_notes(self._notes_for_current_subfolder())
        for n in notes:
            self.note_store.append([n.display_name(), n.path, n.mtime])

        if select_path:
            # Re-select a specific note by its file path after reload.
            for row in self.note_store:
                if row[1] == select_path:
                    self.note_view.get_selection().select_iter(row.iter)
                    break
        self.update_status()

    # ----------------------------------------------------------- editor -- #
    def _clear_editor(self):
        self._loading = True
        self.text_buffer.set_text("")
        self._loading = False
        self._dirty = False

    def _load_note(self, note):
        try:
            with open(note.path, "r", encoding="utf-8") as fh:
                content = fh.read()
        except (OSError, UnicodeDecodeError) as exc:
            self._error_dialog(f"Could not open note:\n{exc}")
            return
        self._loading = True
        self.text_buffer.set_text(content)
        self._loading = False
        self.current_note = note
        self._dirty = False
        self.highlighter.highlight()
        self.update_status()

    def _save_current(self):
        if not self.current_note:
            return False
        start = self.text_buffer.get_start_iter()
        end = self.text_buffer.get_end_iter()
        content = self.text_buffer.get_text(start, end, True)
        try:
            with open(self.current_note.path, "w", encoding="utf-8") as fh:
                fh.write(content)
        except OSError as exc:
            self._error_dialog(f"Could not save note:\n{exc}")
            return False
        self.current_note.mtime = time.time()
        self._dirty = False
        self.update_status()
        return True

    # --------------------------------------------------------- handlers -- #
    def on_sidebar_selection_changed(self, selection):
        model, treeiter = selection.get_selected()
        if treeiter is None:
            return
        is_all = model[treeiter][2]
        if is_all:
            self.current_subfolder = ALL_NOTES
        else:
            self.current_subfolder = model[treeiter][1]
        self.current_note = None
        self._clear_editor()
        self._reload_notelist()

    def on_note_selection_changed(self, selection):
        model, treeiter = selection.get_selected()
        if treeiter is None:
            return
        if self._maybe_warn_unsaved() is False:
            return
        path = model[treeiter][1]
        self._load_note(Note(path))

    def on_text_changed(self, _buffer):
        if self._loading:
            return
        self._dirty = True
        self.highlighter.highlight()
        self.update_status()

    def on_new_note(self, _widget):
        if not self.root_folder:
            self._error_dialog("Open a working folder first (Ctrl+O).")
            return
        # Target folder = currently selected subfolder, else the root.
        if self.current_subfolder is ALL_NOTES:
            target_dir = self.root_folder
        else:
            target_dir = os.path.join(self.root_folder, self.current_subfolder)

        path = self._unique_note_path(target_dir)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("")
        except OSError as exc:
            self._error_dialog(f"Could not create note:\n{exc}")
            return
        self._reload_notelist(select_path=path)
        self._load_note(Note(path))
        self.text_view.grab_focus()

    def _unique_note_path(self, folder):
        base = "Untitled"
        candidate = os.path.join(folder, base + ".md")
        i = 1
        while os.path.exists(candidate):
            candidate = os.path.join(folder, f"{base} {i}.md")
            i += 1
        return candidate

    def on_save_note(self, _widget):
        self._save_current()

    def on_open_folder(self, _widget):
        dialog = Gtk.FileChooserDialog(
            title="Open Working Folder",
            parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        dialog.add_buttons(
            "_Cancel", Gtk.ResponseType.CANCEL,
            "_Open", Gtk.ResponseType.OK,
        )
        if self.root_folder:
            dialog.set_current_folder(self.root_folder)
        if dialog.run() == Gtk.ResponseType.OK:
            folder = dialog.get_filename()
            dialog.destroy()
            self.open_folder(folder)
        else:
            dialog.destroy()

    def on_sort_changed(self, widget, mode):
        if widget.get_active():
            self.sort_mode = mode
            keep = self.current_note.path if self.current_note else None
            self._reload_notelist(select_path=keep)

    def on_quit(self, _widget):
        if self._maybe_warn_unsaved() is False:
            return
        Gtk.main_quit()

    def _on_delete_event(self, _widget, _event):
        if self._maybe_warn_unsaved() is False:
            return True  # cancel close
        return False

    # ---------------------------------------------------------- dialogs -- #
    def _maybe_warn_unsaved(self):
        """
        If there are unsaved changes, ask the user. Returns False if the
        pending action should be cancelled, True otherwise.
        """
        if not self._dirty or not self.current_note:
            return True
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text="Save changes to the current note?",
        )
        dialog.add_buttons(
            "Discard", Gtk.ResponseType.NO,
            "_Cancel", Gtk.ResponseType.CANCEL,
            "_Save", Gtk.ResponseType.YES,
        )
        resp = dialog.run()
        dialog.destroy()
        if resp == Gtk.ResponseType.YES:
            self._save_current()
            return True
        if resp == Gtk.ResponseType.NO:
            self._dirty = False
            return True
        return False  # cancelled

    def _error_dialog(self, message):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=message,
        )
        dialog.run()
        dialog.destroy()


def main():
    root = None
    if len(sys.argv) > 1:
        root = sys.argv[1]

    win = NotebookWindow(root_folder=root)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
