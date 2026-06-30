"""
gtk3_panes.py — GTK3 construction + data-binding for the four panes.

A **mixin** combined into NotebookWindow in gtk3_window.py. Builds the sidebar
(pane 1), note list (pane 2), editor host (pane 3, a Gtk.Notebook of EditorTabs),
the headings-outline (pane 4), and the status bar; plus the reload / cell-render /
selection helpers that populate panes 1, 2 and 4 from qdvcmdnb_lib.model.
GTK3-specific; relies on attributes/handlers defined across the window and its
other mixins.

User-facing text comes from qdvcmdnb_lib.strings (Sidebar namespace).
"""

import os
from xml.sax.saxutils import escape as _xml_escape

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango  # noqa: E402

from . import model
from .config import (
    NODE_ALL_NOTES,
    NODE_INBOX,
    NODE_EMPTY_NOTES,
    NODE_SUBFOLDERS,
    NODE_SUBFOLDER,
)
from .strings import Sidebar as S


class PanesMixin:
    """Pane construction + data binding for NotebookWindow (see module docstring)."""

    def _build_sidebar(self):
        # Build pane 1: a tree of "All Notes / Inbox / Empty Notes / Subfolders".
        #
        # GTK notes for non-GTK readers:
        #  * A Gtk.ScrolledWindow wraps a child so it gains scrollbars; the policy
        #    AUTOMATIC means "show a scrollbar only when needed".
        #  * The data lives in a Gtk.TreeStore (a tree-shaped table of typed
        #    columns); the Gtk.TreeView is the widget that renders it. They are
        #    kept separate (model/view): here the store has four str columns.
        #  * A TreeViewColumn draws cells via "cell renderers". We pack a pixbuf
        #    renderer (the icon) and a text renderer, then add_attribute maps a
        #    store column index to a renderer property ("icon-name"/"text").
        #  * get_selection() returns the selection object; its "changed" signal
        #    fires when the highlighted row changes.
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        # Columns: icon name (str), display label (str), node kind (str),
        #          subfolder name (str, only meaningful for NODE_SUBFOLDER)
        self.sidebar_store = Gtk.TreeStore(str, str, str, str)
        self.sidebar_view = Gtk.TreeView(model=self.sidebar_store)
        self.sidebar_view.set_headers_visible(False)

        col = Gtk.TreeViewColumn(S.FOLDERS_COLUMN)
        icon_renderer = Gtk.CellRendererPixbuf()
        text_renderer = Gtk.CellRendererText()
        col.pack_start(icon_renderer, False)
        col.pack_start(text_renderer, True)
        col.add_attribute(icon_renderer, "icon-name", 0)
        col.add_attribute(text_renderer, "text", 1)
        self.sidebar_view.append_column(col)

        self.sidebar_view.get_selection().connect(
            "changed", self.on_sidebar_selection_changed)

        scroll.add(self.sidebar_view)
        return scroll

    def _build_notelist(self):
        # Build pane 2: a search row stacked above the note list.
        #
        # GTK notes:
        #  * A Gtk.Box packs children in a row/column; pack_start(child, expand,
        #    fill, padding) adds them left-to-right (or top-to-bottom for VERTICAL).
        #  * A Gtk.Entry is a single-line text field; set_placeholder_text shows
        #    grey hint text when empty; its "activate" signal fires on ENTER. We
        #    also add a clickable clear icon inside it ("icon-press" signal).
        #  * A Gtk.Stack holds several children but shows one at a time by name —
        #    here the real list vs a placeholder for the Subfolders parent node.
        #  * The list is a ListStore (flat table) shown by a TreeView. The text
        #    renderer's "ellipsize" trims long titles with an ellipsis, and a
        #    cell-data-func lets us compute each cell's markup at draw time.
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # --- search row ---
        search_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        search_row.set_margin_start(4)
        search_row.set_margin_end(4)
        search_row.set_margin_top(4)
        search_row.set_margin_bottom(4)

        self.search_entry = Gtk.Entry()
        self.search_entry.set_placeholder_text(S.SEARCH_PLACEHOLDER)
        self.search_entry.set_hexpand(True)
        # Only search on ENTER (the "activate" signal), not on every keystroke.
        self.search_entry.connect("activate", self.on_search)
        # A clear icon inside the entry; clearing resets the filter.
        self.search_entry.set_icon_from_icon_name(
            Gtk.EntryIconPosition.SECONDARY, "edit-clear-symbolic")
        self.search_entry.connect("icon-press", self.on_search_icon_press)
        search_row.pack_start(self.search_entry, True, True, 0)

        search_btn = Gtk.Button(label=S.SEARCH_BUTTON)
        search_btn.set_image(Gtk.Image.new_from_icon_name(
            "edit-find", Gtk.IconSize.BUTTON))
        search_btn.set_always_show_image(True)
        search_btn.connect("clicked", self.on_search)
        search_row.pack_start(search_btn, False, False, 0)

        outer.pack_start(search_row, False, False, 0)

        # The active search query (None means no filter).
        self.search_query = None

        # A Stack: the scrolled note list, plus a placeholder shown when the
        # "Subfolders" parent node is selected.
        self.notelist_stack = Gtk.Stack()

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        # Columns: display name (str), full path (str), mtime (float),
        #          first-body-line snippet (str). The visible markup is built at
        #          draw time by a cell-data-func so it can depend on selection
        #          state (the card sub-lines lighten when the row is selected).
        self.note_store = Gtk.ListStore(str, str, float, str)
        self.note_view = Gtk.TreeView(model=self.note_store)
        self.note_view.set_headers_visible(False)

        renderer = Gtk.CellRendererText()
        renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
        col = Gtk.TreeViewColumn(S.NOTES_COLUMN, renderer)
        col.set_cell_data_func(renderer, self._note_cell_data)
        self.note_view.append_column(col)

        self.note_view.get_selection().connect(
            "changed", self.on_note_selection_changed)
        # "button-press-event" delivers raw mouse clicks (used for right-click).
        self.note_view.connect("button-press-event",
                               self.on_notelist_button_press)

        scroll.add(self.note_view)
        # add_named registers each child under a key; set_visible_child_name
        # picks which one is shown.
        self.notelist_stack.add_named(scroll, "list")
        self.notelist_stack.add_named(
            self._make_placeholder(S.NOTELIST_PLACEHOLDER), "placeholder")
        self.notelist_stack.set_visible_child_name("list")
        outer.pack_start(self.notelist_stack, True, True, 0)
        return outer

    @staticmethod
    def _make_placeholder(text):
        # A centred, dim message used as a Stack page when there's nothing to
        # list. set_markup interprets Pango markup (an HTML-like styling string);
        # halign/valign CENTER centre the box within the available space.
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_valign(Gtk.Align.CENTER)
        box.set_halign(Gtk.Align.CENTER)
        label = Gtk.Label()
        label.set_markup(
            f"<span size='large' foreground='#888888'>{text}</span>")
        box.add(label)
        return box

    def _show_notelist_placeholder(self):
        # Switch pane 2 to its placeholder page and clear the backing list.
        self.note_store.clear()
        self.notelist_stack.set_visible_child_name("placeholder")
        self.update_status()

    def _build_editor(self):
        # Build pane 3: the editor host. A Gtk.Notebook is the tabbed container;
        # each page is an EditorTab (added later in _new_tab). set_scrollable
        # adds arrows when tabs overflow; "switch-page" fires when the active tab
        # changes. We hide the tab strip while there's only one tab.
        self.notebook = Gtk.Notebook()
        self.notebook.set_scrollable(True)
        self.notebook.set_show_border(False)
        # The tab bar is hidden whenever there is a single tab (see
        # _update_tabbar_visibility). show-tabs starts False for the initial tab.
        self.notebook.set_show_tabs(False)
        self.notebook.connect("switch-page", self.on_tab_switched)
        self._tabs = []  # list[EditorTab], parallel to notebook pages
        return self.notebook

    def _build_outline(self):
        """
        Pane 4: a tree of the current note's markdown headings. Each row stores
        the heading title and the 0-based source line to jump to. Hidden until
        toggled on (the toggle calls _apply_outline_visibility).

        Like the sidebar, this is a TreeStore + TreeView. "row-activated" fires on
        double-click/Enter and the selection's "changed" fires on single click;
        both jump to the heading. set_no_show_all(True) means a blanket
        show_all() on the window won't reveal this pane — we show it explicitly
        only when the outline toggle is on.
        """
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.outline_scroll = scroll

        # Columns: display label (str), source line index (int).
        self.outline_store = Gtk.TreeStore(str, int)
        self.outline_view = Gtk.TreeView(model=self.outline_store)
        self.outline_view.set_headers_visible(False)
        # Shorthand column: bind store column 0 directly to the renderer's text.
        col = Gtk.TreeViewColumn(S.OUTLINE_COLUMN, Gtk.CellRendererText(),
                                 text=0)
        self.outline_view.append_column(col)
        self.outline_view.connect("row-activated", self.on_outline_row_activated)
        # Single click should jump too (not just double-click/Enter).
        self.outline_view.get_selection().connect(
            "changed", self.on_outline_selection_changed)
        self._outline_guard = False

        scroll.add(self.outline_view)
        scroll.set_no_show_all(True)  # stays hidden until explicitly shown
        return scroll

    def _build_statusbar(self):
        # Build the footer: a bold mode indicator on the left, then a normal
        # Gtk.Statusbar filling the rest. A Statusbar shows messages from a
        # context (an id from get_context_id); push() adds a message and pop()
        # removes the top one (we pop+push to replace text in update_status).
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.statusbar_box = box
        self.mode_label = Gtk.Label()
        self.mode_label.set_margin_start(6)
        self.mode_label.set_margin_end(6)
        box.pack_start(self.mode_label, False, False, 0)
        self.statusbar = Gtk.Statusbar()
        self._status_ctx = self.statusbar.get_context_id("main")
        box.pack_start(self.statusbar, True, True, 0)
        return box

    def _reload_sidebar(self, preserve_selection=False):
        # Rebuild pane 1's rows from the current workspace. TreeStore.append
        # (parent, row) adds a row; parent=None means top level, and passing a
        # parent iter nests the row beneath it (the subfolders under "Subfolders").
        # Remember the current selection so a refresh doesn't reset it.
        prev_node = self.current_node
        prev_sub = self.current_subfolder

        self.sidebar_store.clear()
        # Row schema: [icon_name, label, node_kind, subfolder_name]
        self.sidebar_store.append(
            None, ["emblem-documents", S.ALL_NOTES, NODE_ALL_NOTES, ""])
        # Inbox: notes sitting at the top level (not yet filed into a subfolder).
        self.sidebar_store.append(
            None, ["mail-inbox", S.INBOX, NODE_INBOX, ""])
        self.sidebar_store.append(
            None, ["edit-clear", S.EMPTY_NOTES, NODE_EMPTY_NOTES, ""])

        subfolders_iter = self.sidebar_store.append(
            None, ["folder", S.SUBFOLDERS, NODE_SUBFOLDERS, ""])
        if self.root_folder:
            for sub in model.immediate_subfolders(self.root_folder):
                self.sidebar_store.append(
                    subfolders_iter, ["folder", sub, NODE_SUBFOLDER, sub])

        # expand_all opens every tree row so the Subfolders children are visible.
        self.sidebar_view.expand_all()

        if preserve_selection and prev_node is not None:
            # Restore the prior selection if it still exists; else fall back to
            # All Notes. _select_sidebar_node reloads pane 2 via its handler.
            if not self._select_sidebar_node(prev_node, prev_sub):
                self.sidebar_view.get_selection().select_path(
                    Gtk.TreePath.new_first())
        else:
            # Default: select "All Notes" (TreePath.new_first = the first row).
            self.sidebar_view.get_selection().select_path(
                Gtk.TreePath.new_first())

    def _notes_for_current_subfolder(self):
        # Pure dispatch (no GTK): pick the model query for the selected sidebar
        # node and return a list of Note objects. The window/handlers turn this
        # into rows in _reload_notelist.
        if not self.root_folder:
            return []
        if self.current_node == NODE_ALL_NOTES:
            return model.collect_notes(self.root_folder)
        if self.current_node == NODE_INBOX:
            return model.collect_top_level_notes(self.root_folder)
        if self.current_node == NODE_EMPTY_NOTES:
            return model.collect_empty_notes(self.root_folder)
        if self.current_node == NODE_SUBFOLDER and self.current_subfolder:
            folder = os.path.join(self.root_folder, self.current_subfolder)
            return model.collect_notes(folder)
        # NODE_SUBFOLDERS (parent) or anything else: no list.
        return []

    def _reload_notelist(self, select_path=None):
        # Refill pane 2 from disk. We clear the ListStore and append one row per
        # note (append takes a list matching the store's column types). Optionally
        # re-select a row by its file path afterwards. Each row.iter is the
        # TreeIter (a handle to that row) the selection needs.
        self.notelist_stack.set_visible_child_name("list")
        self.note_store.clear()
        notes = model.sort_notes(
            self._notes_for_current_subfolder(), self.sort_mode)

        # Apply the search filter, if any. Matching is case-insensitive against
        # the note's name AND its full contents (see model.note_matches). A
        # blank/None query means no filtering.
        if (self.search_query or "").strip():
            filtered = model.filter_notes(notes, self.search_query)
            self._search_no_results = (len(filtered) == 0)
            notes = filtered
        else:
            self._search_no_results = False

        for n in notes:
            self.note_store.append(
                [n.display_name(), n.path, n.mtime,
                 model.first_body_line(n)])

        if select_path:
            # Re-select a specific note by its file path after reload.
            for row in self.note_store:
                if row[1] == select_path:
                    self.note_view.get_selection().select_iter(row.iter)
                    break
        self.update_status()

    def _note_cell_data(self, _col, cell, store, treeiter, _data):
        """
        Build the cell markup at draw time. GTK calls this "cell-data-func" for
        every visible row just before painting, passing the cell renderer and the
        row (store + treeiter); we set the renderer's properties to control what
        that row shows. This lets one renderer paint either a plain title (list
        view) or a multi-line card (card view).

        In list view it's just the title. In card view it's three lines: bold
        title, then the last-modified date and the first body line. The sub-lines
        use the same colour as the title (so nothing clashes with the selection
        highlight) but are italicised and slightly smaller to set them apart.
        Card rows also get a little extra top/bottom padding via "ypad".
        """
        title = _xml_escape(store[treeiter][0])
        if not self.card_view:
            cell.set_property("ypad", 0)
            cell.set_property("markup", title)
            return

        mtime = store[treeiter][2]
        date = _xml_escape(model.format_mtime_value(mtime))
        snippet = _xml_escape(store[treeiter][3])

        sub = (f"\n<i><span size='small'>{date}</span></i>"
               if date else "")
        sub += (f"\n<i><span size='small'>{snippet}</span></i>"
                if snippet else "")
        cell.set_property("ypad", 2)  # ~2px extra top & bottom in card view
        cell.set_property("markup", f"<b>{title}</b>{sub}")

    def _select_sidebar_node(self, node_kind, subfolder=None):
        """
        Programmatically select a sidebar row by kind (and subfolder name).
        Returns True if a matching row was found and selected, else False.

        TreeModel.foreach walks every row, calling our callback with
        (model, path, iter); returning True from the callback stops the walk.
        We use a one-key dict as a mutable flag because the nested function can't
        rebind a plain local from the enclosing scope. expand_to_path opens any
        parent rows so the target is visible before selecting it.
        """
        found = {"hit": False}

        def _match(model_, _path, treeiter):
            if model_[treeiter][2] != node_kind:
                return False
            if node_kind == NODE_SUBFOLDER and model_[treeiter][3] != subfolder:
                return False
            self.sidebar_view.expand_to_path(model_.get_path(treeiter))
            self.sidebar_view.get_selection().select_iter(treeiter)
            found["hit"] = True
            return True  # stop iteration

        self.sidebar_store.foreach(_match)
        return found["hit"]

    def _refresh_outline(self):
        """
        Rebuild the outline tree (pane 4) from the active tab's current text.

        Headings come from model.parse_headings (pure parsing, no GTK). We turn
        the flat list into a nested TreeStore by tracking a stack of open
        (level, row) frames: before adding a heading we pop frames whose level is
        >= the new one, so the new row nests under the nearest shallower heading.
        The _outline_guard flag suppresses the selection-"changed" handler while
        we rebuild (otherwise clearing/refilling would fire spurious jumps).
        """
        if not getattr(self, "outline_visible", False):
            return
        self._outline_guard = True
        try:
            self.outline_store.clear()
            tab = self._active_tab()
            if tab is None or tab.note is None:
                self._outline_guard = False
                return
            headings = model.parse_headings(tab.get_content())
            # Build a simple nested tree by heading level using a stack of
            # (level, iter) frames; deeper levels nest under shallower ones.
            stack = []  # list of (level, treeiter)
            for h in headings:
                level = h["level"]
                while stack and stack[-1][0] >= level:
                    stack.pop()
                parent = stack[-1][1] if stack else None
                it = self.outline_store.append(
                    parent, [h["title"], h["line"]])
                stack.append((level, it))
            self.outline_view.expand_all()
        finally:
            self._outline_guard = False

    def _apply_outline_visibility(self):
        """Show/hide the outline pane and (re)build it when shown.

        Because the pane has set_no_show_all(True), we must call show()/
        show_all() on it explicitly to reveal it (and its child rows); hide()
        collapses it back out of the layout.
        """
        if self.outline_visible:
            self.outline_scroll.show()
            self.outline_view.show_all()
            self._refresh_outline()
        else:
            self.outline_scroll.hide()

    def on_outline_row_activated(self, _view, path, _col):
        # "row-activated" handler (double-click/Enter on an outline row). GTK
        # passes the tree path of the activated row; we look up its stored source
        # line (column 1) and jump the editor there.
        treeiter = self.outline_store.get_iter(path)
        self._jump_to_outline_line(self.outline_store[treeiter][1])

    def on_outline_selection_changed(self, selection):
        # Selection "changed" handler (single click). Skipped while we are
        # rebuilding the tree (_outline_guard). get_selected() returns
        # (model, iter); iter is None if nothing is selected.
        if self._outline_guard:
            return
        _model, treeiter = selection.get_selected()
        if treeiter is None:
            return
        self._jump_to_outline_line(_model[treeiter][1])

    def _jump_to_outline_line(self, line_index):
        # Ask the active tab to scroll its editor to the given source line. No GTK
        # here directly — the tab owns the TextView and does the scrolling.
        tab = self._active_tab()
        if tab is not None and tab.note is not None:
            tab.scroll_to_line(line_index)
