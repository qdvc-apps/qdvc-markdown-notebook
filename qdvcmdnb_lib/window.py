"""
window.py — NotebookWindow: the view + controller for QDVC Markdown Notebook.

GTK and controller logic live together here, which is idiomatic for GTK (signal
handlers are wired directly to widgets). All filesystem and business logic is
delegated to qdvcmdnb_lib.model so this layer never touches disk directly.
"""

import os

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango  # noqa: E402

from . import model
from .config import (
    APP_NAME,
    SORT_ALPHA,
    SORT_DATE_NEW,
    SORT_DATE_OLD,
    ALL_NOTES,
)
from .settings import Settings
from .editortab import EditorTab


class NotebookWindow(Gtk.Window):

    def __init__(self, root_folder=None):
        super().__init__(title=APP_NAME)
        self.set_default_size(1000, 640)

        self.settings = Settings.load()

        self.root_folder = None
        self.current_subfolder = ALL_NOTES
        self.sort_mode = SORT_ALPHA
        self._note_select_guard = False   # suppress reselection feedback loops

        self._build_ui()
        # Start with one empty tab.
        self._new_tab(focus=False)
        self._apply_editor_font()
        self._rebuild_recent_menu()

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
        self._accel_group = accel

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

        # "Open Recent" submenu, populated dynamically from settings.
        self.recent_menu_item = Gtk.MenuItem(label="Open Recent")
        self.recent_menu = Gtk.Menu()
        self.recent_menu_item.set_submenu(self.recent_menu)
        file_menu.append(self.recent_menu_item)

        file_menu.append(Gtk.SeparatorMenuItem())

        mi_new_tab = Gtk.MenuItem(label="New Tab")
        mi_new_tab.add_accelerator("activate", accel, Gdk.KEY_t,
                                   Gdk.ModifierType.CONTROL_MASK,
                                   Gtk.AccelFlags.VISIBLE)
        mi_new_tab.connect("activate", self.on_new_tab)
        file_menu.append(mi_new_tab)

        mi_close_tab = Gtk.MenuItem(label="Close Tab")
        mi_close_tab.add_accelerator("activate", accel, Gdk.KEY_w,
                                     Gdk.ModifierType.CONTROL_MASK,
                                     Gtk.AccelFlags.VISIBLE)
        mi_close_tab.connect("activate", self.on_close_tab)
        file_menu.append(mi_close_tab)

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

        mi_alpha = Gtk.RadioMenuItem(label="Sort: Alphabetical", group=None)
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

        view_menu.append(Gtk.SeparatorMenuItem())

        mi_font = Gtk.MenuItem(label="Set Editor Font\u2026")
        mi_font.connect("activate", self.on_choose_font)
        view_menu.append(mi_font)

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
        self.note_view.connect("button-press-event",
                               self.on_notelist_button_press)

        scroll.add(self.note_view)
        return scroll

    def _build_editor(self):
        # The editor area is a Gtk.Notebook; each page is an EditorTab.
        self.notebook = Gtk.Notebook()
        self.notebook.set_scrollable(True)
        self.notebook.set_show_border(False)
        # The tab bar is hidden whenever there is a single tab (see
        # _update_tabbar_visibility). show-tabs starts False for the initial tab.
        self.notebook.set_show_tabs(False)
        self.notebook.connect("switch-page", self.on_tab_switched)
        self._tabs = []  # list[EditorTab], parallel to notebook pages
        return self.notebook

    def _build_statusbar(self):
        self.statusbar = Gtk.Statusbar()
        self._status_ctx = self.statusbar.get_context_id("main")
        return self.statusbar

    # ----------------------------------------------------------- settings -- #
    def _apply_editor_font(self):
        """Apply the editor font from settings to every open tab."""
        for tab in self._tabs:
            tab.apply_font(self.settings.editor_font)

    # --------------------------------------------------------------- tabs -- #
    def _active_tab(self):
        idx = self.notebook.get_current_page()
        if idx < 0 or idx >= len(self._tabs):
            return None
        return self._tabs[idx]

    def _new_tab(self, focus=True):
        """Create, append, and (optionally) switch to a new empty tab."""
        tab = EditorTab(on_changed=self._on_tab_changed,
                        on_close=self._close_tab)
        tab.apply_font(self.settings.editor_font)
        self._tabs.append(tab)
        idx = self.notebook.append_page(tab.widget, tab.tab_label)
        self.notebook.set_tab_reorderable(tab.widget, True)
        self._update_tabbar_visibility()
        if focus:
            self.notebook.set_current_page(idx)
            tab.text_view.grab_focus()
        self.update_status()
        return tab

    def _close_tab(self, tab):
        """Close `tab`, prompting if it has unsaved changes. No-op if last tab."""
        if len(self._tabs) <= 1:
            return  # never close the final tab; tab bar is hidden anyway
        if self._maybe_warn_unsaved(tab) is False:
            return
        idx = self._tabs.index(tab)
        self.notebook.remove_page(idx)
        self._tabs.pop(idx)
        self._update_tabbar_visibility()
        self.update_status()

    def _update_tabbar_visibility(self):
        """Show the tab bar only when more than one tab is open."""
        self.notebook.set_show_tabs(len(self._tabs) > 1)

    def _on_tab_changed(self, _tab):
        """Called by a tab when its buffer is edited."""
        self.update_status()

    def _rebuild_recent_menu(self):
        """Repopulate the File > Open Recent submenu from settings."""
        for child in self.recent_menu.get_children():
            self.recent_menu.remove(child)

        recents = self.settings.recent_folders
        if not recents:
            placeholder = Gtk.MenuItem(label="(none)")
            placeholder.set_sensitive(False)
            self.recent_menu.append(placeholder)
        else:
            for folder in recents:
                item = Gtk.MenuItem(label=folder)
                item.connect("activate", self.on_open_recent, folder)
                self.recent_menu.append(item)
        self.recent_menu.show_all()

    def _remember_folder(self, folder):
        """Record a folder as recent, persist, and refresh the menu."""
        self.settings.add_recent_folder(folder)
        self.settings.save()
        self._rebuild_recent_menu()

    # -------------------------------------------------------- status bar -- #
    def update_status(self):
        count = len(self.note_store)
        tab = self._active_tab()
        if tab and tab.note:
            sel = tab.note.display_name()
        else:
            sel = "none"
        msg = f"{count} item(s)  |  Selected: {sel}"
        if tab and tab.dirty:
            msg += "  *"
        if len(self._tabs) > 1:
            msg += f"  |  Tab {self.notebook.get_current_page() + 1}" \
                   f"/{len(self._tabs)}"
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
        self._reload_sidebar()
        self._reload_notelist()
        tab = self._active_tab()
        if tab:
            tab.clear()
        self.update_status()
        self._remember_folder(folder)

    def _reload_sidebar(self):
        self.sidebar_store.clear()
        # Top segment: "All Notes".
        self.sidebar_store.append(None, ["All Notes", "", True])
        # Bottom segment: immediate subfolders.
        if self.root_folder:
            for sub in model.immediate_subfolders(self.root_folder):
                self.sidebar_store.append(None, [sub, sub, False])
        # Select "All Notes" by default.
        self.sidebar_view.get_selection().select_path(Gtk.TreePath.new_first())

    def _notes_for_current_subfolder(self):
        if not self.root_folder:
            return []
        if self.current_subfolder is ALL_NOTES:
            return model.collect_notes(self.root_folder)
        folder = os.path.join(self.root_folder, self.current_subfolder)
        return model.collect_notes(folder)

    def _reload_notelist(self, select_path=None):
        self.note_store.clear()
        notes = model.sort_notes(
            self._notes_for_current_subfolder(), self.sort_mode)
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
    def _load_note_in_active_tab(self, note):
        tab = self._active_tab()
        if tab is None:
            tab = self._new_tab(focus=True)
        if not tab.load_note(note):
            self._error_dialog(f"Could not open note:\n{note.path}")
            return
        self.update_status()

    def _load_note_in_new_tab(self, note):
        tab = self._new_tab(focus=True)
        if not tab.load_note(note):
            self._error_dialog(f"Could not open note:\n{note.path}")
            return
        self.update_status()

    def _save_active(self):
        tab = self._active_tab()
        if tab is None or not tab.note:
            return False
        if not tab.save():
            self._error_dialog(f"Could not save note:\n{tab.note.path}")
            return False
        self.update_status()
        return True

    # --------------------------------------------------------- handlers -- #
    def on_sidebar_selection_changed(self, selection):
        model_, treeiter = selection.get_selected()
        if treeiter is None:
            return
        is_all = model_[treeiter][2]
        if is_all:
            self.current_subfolder = ALL_NOTES
        else:
            self.current_subfolder = model_[treeiter][1]
        self._reload_notelist()

    def on_note_selection_changed(self, selection):
        if self._note_select_guard:
            return
        model_, treeiter = selection.get_selected()
        if treeiter is None:
            return
        # Default behaviour: open (replace) in the active tab.
        tab = self._active_tab()
        if tab and self._maybe_warn_unsaved(tab) is False:
            # User cancelled; revert the selection to the tab's current note.
            self._reselect_active_note()
            return
        path = model_[treeiter][1]
        self._load_note_in_active_tab(model.Note(path))

    def on_notelist_button_press(self, _widget, event):
        # Right-click (button 3) opens the context menu on the row under it.
        if event.button != 3:
            return False
        path_info = self.note_view.get_path_at_pos(int(event.x), int(event.y))
        if path_info is None:
            return False
        path, _col, _cx, _cy = path_info
        self.note_view.get_selection().select_path(path)
        treeiter = self.note_store.get_iter(path)
        note_path = self.note_store[treeiter][1]

        menu = Gtk.Menu()
        item = Gtk.MenuItem(label="Open in new tab")
        item.connect("activate",
                     lambda _i: self._load_note_in_new_tab(model.Note(note_path)))
        menu.append(item)
        menu.show_all()
        menu.popup_at_pointer(event)
        return True

    def on_tab_switched(self, _notebook, _page, _page_num):
        # GTK fires this during construction too; guard via _tabs presence.
        if getattr(self, "_tabs", None):
            self.update_status()

    def on_new_tab(self, _widget):
        self._new_tab(focus=True)

    def on_close_tab(self, _widget):
        tab = self._active_tab()
        if tab is not None:
            self._close_tab(tab)

    def on_new_note(self, _widget):
        if not self.root_folder:
            self._error_dialog("Open a working folder first (Ctrl+O).")
            return
        # Target folder = currently selected subfolder, else the root.
        if self.current_subfolder is ALL_NOTES:
            target_dir = self.root_folder
        else:
            target_dir = os.path.join(self.root_folder, self.current_subfolder)

        try:
            path = model.create_empty_note(target_dir)
        except OSError as exc:
            self._error_dialog(f"Could not create note:\n{exc}")
            return
        self._reload_notelist(select_path=path)
        self._load_note_in_active_tab(model.Note(path))
        tab = self._active_tab()
        if tab:
            tab.text_view.grab_focus()

    def on_save_note(self, _widget):
        self._save_active()

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

    def on_open_recent(self, _widget, folder):
        if not os.path.isdir(folder):
            self._error_dialog(f"Folder no longer exists:\n{folder}")
            # Drop the dead entry and refresh.
            self.settings.recent_folders = [
                f for f in self.settings.recent_folders if f != folder
            ]
            self.settings.save()
            self._rebuild_recent_menu()
            return
        if self._maybe_warn_unsaved(self._active_tab()) is False:
            return
        self.open_folder(folder)

    def on_choose_font(self, _widget):
        dialog = Gtk.FontChooserDialog(title="Set Editor Font", parent=self)
        dialog.set_font(self.settings.editor_font)
        # Only the markdown editor is themed; a sample hints at the use.
        dialog.set_preview_text("# Heading\nBody text 0123 *italic* `code`")
        if dialog.run() == Gtk.ResponseType.OK:
            chosen = dialog.get_font()
            if chosen:
                self.settings.set_editor_font(chosen)
                self.settings.save()
                self._apply_editor_font()
        dialog.destroy()

    def on_sort_changed(self, widget, mode):
        if widget.get_active():
            self.sort_mode = mode
            tab = self._active_tab()
            keep = tab.note.path if (tab and tab.note) else None
            self._reload_notelist(select_path=keep)

    def _reselect_active_note(self):
        """
        After a cancelled note switch, restore the list selection to whatever
        the active tab currently holds (or clear it). Guarded so the
        selection-changed handler does not re-trigger a load.
        """
        tab = self._active_tab()
        target = tab.note.path if (tab and tab.note) else None
        self._note_select_guard = True
        try:
            sel = self.note_view.get_selection()
            sel.unselect_all()
            if target:
                for row in self.note_store:
                    if row[1] == target:
                        sel.select_iter(row.iter)
                        break
        finally:
            self._note_select_guard = False

    def on_quit(self, _widget):
        if self._confirm_close_all() is False:
            return
        Gtk.main_quit()

    def _on_delete_event(self, _widget, _event):
        if self._confirm_close_all() is False:
            return True  # cancel close
        return False

    def _confirm_close_all(self):
        """Prompt for every dirty tab before quitting. False cancels the quit."""
        for tab in list(self._tabs):
            if self._maybe_warn_unsaved(tab) is False:
                return False
        return True

    # ---------------------------------------------------------- dialogs -- #
    def _maybe_warn_unsaved(self, tab):
        """
        If `tab` has unsaved changes, ask the user. Returns False if the pending
        action should be cancelled, True otherwise. A None tab is treated as
        clean (nothing to lose).
        """
        if tab is None or not tab.dirty or not tab.note:
            return True
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text=f"Save changes to \u201c{tab.note.display_name()}\u201d?",
        )
        dialog.add_buttons(
            "Discard", Gtk.ResponseType.NO,
            "_Cancel", Gtk.ResponseType.CANCEL,
            "_Save", Gtk.ResponseType.YES,
        )
        resp = dialog.run()
        dialog.destroy()
        if resp == Gtk.ResponseType.YES:
            tab.save()
            return True
        if resp == Gtk.ResponseType.NO:
            tab.dirty = False
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
