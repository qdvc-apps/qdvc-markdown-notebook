"""
gtk3_window.py — NotebookWindow: the GTK3 view + controller core.

NotebookWindow is the top-level Gtk.Window. To keep this file readable, most of
its widget-construction and handler methods are factored into mixins (one file
per concern), and composed here via multiple inheritance:

    MenuBarMixin   gtk3_menubar.py   — the menu bar
    ToolbarMixin   gtk3_toolbar.py   — the toolbar + its styling
    PanesMixin     gtk3_panes.py     — the four panes + their data binding
    ActionsMixin   gtk3_actions.py   — user-action handlers, menus, dialogs

This core keeps the window lifecycle (__init__, _build_ui), the icon-set / session
restore, the live font/spacing appliers, the view-toggle state machine
(read-only / preview / card view / outline) with its menu↔toolbar sync, tab
management, the status bar, and open_folder + the recent-workspace menu.

All of this layer is GTK3-specific (hence the gtk3_ prefix). Filesystem and
business logic is delegated to the GTK-free core modules (config, model,
settings, pango_markdown) so a future GTK4 view could reuse them unchanged. See
MAINTENANCE.md.
"""

import os

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib  # noqa: E402

from . import model
from .config import (
    APP_NAME,
    SORT_ALPHA,
    SORT_DATE_NEW,
    SORT_DATE_OLD,
    NODE_ALL_NOTES,
    NODE_INBOX,
    NODE_EMPTY_NOTES,
    NODE_SUBFOLDERS,
    NODE_SUBFOLDER,
)
from .settings import (
    Settings,
    icon_set_files,
    install_icon_set,
    uninstall_icon_set,
    update_desktop_icon,
    APP_ICON_NAME,
)
from .gtk3_editortab import EditorTab
from .gtk3_menubar import MenuBarMixin
from .gtk3_toolbar import ToolbarMixin
from .gtk3_panes import PanesMixin
from .gtk3_actions import ActionsMixin
from . import strings
from .strings import Status, Menu


class NotebookWindow(MenuBarMixin, ToolbarMixin, PanesMixin, ActionsMixin,
                     Gtk.Window):
    def __init__(self, root_folder=None):
        super().__init__(title=APP_NAME)
        self.set_default_size(1000, 640)
        # Center on screen at startup (#1) rather than the WM's default corner.
        self.set_position(Gtk.WindowPosition.CENTER)
        # Window/panel icon (#5). Use the same stock icon named in the .desktop
        # file so the panel/taskbar shows it instead of the generic window icon.
        self.set_icon_name("accessories-text-editor")

        self.settings = Settings.load()
        # Apply a custom icon set (if configured) before anything else shows, so
        # the window/taskbar icon reflects it. Falls back silently to the stock
        # icon on any problem.
        self._apply_icon_set()

        self.root_folder = None
        # Sidebar selection state: a node kind plus, for NODE_SUBFOLDER, the name.
        self.current_node = NODE_ALL_NOTES
        self.current_subfolder = None     # subfolder name when current_node is
                                          # NODE_SUBFOLDER, else None
        # Seed the sort mode from settings when "remember sort order" is on,
        # validating against the known modes.
        self.sort_mode = SORT_ALPHA
        if self.settings.remember_sort and self.settings.sort_mode in (
                SORT_ALPHA, SORT_DATE_NEW, SORT_DATE_OLD):
            self.sort_mode = self.settings.sort_mode
        self._note_select_guard = False   # suppress reselection feedback loops
        self.read_only = True             # (#1) start in read-only mode
        self.preview_mode = False         # rendered-markdown preview (all tabs)
        self.card_view = False            # pane-2 card view (off by default)
        self.outline_visible = False      # headings outline pane (pane 4)
        self.search_query = None          # active note-list search (None = off)
        self._search_no_results = False

        self._build_ui()
        # Start with one empty tab.
        self._new_tab(focus=False)
        self._apply_editor_font()
        self._apply_code_font()
        self._apply_preview_font()
        self._apply_line_spacing()
        self._apply_read_only()
        self._rebuild_recent_menu()

        # Reflect a persisted/restored sort mode in the View-menu radio items
        # (without re-triggering a reload, which the toggle handler guards).
        item = self._sort_items.get(self.sort_mode)
        if item is not None and not item.get_active():
            item.set_active(True)

        if root_folder:
            self.open_folder(os.path.abspath(root_folder))
        elif self.settings.restore_session and self.settings.last_workspace:
            self._restore_last_session()

        # Don't let the first toolbar button take initial keyboard focus (it
        # shows a focus ring / "highlight" on startup otherwise). Put focus on
        # the sidebar instead.
        self.set_focus(self.sidebar_view)

        self.connect("destroy", Gtk.main_quit)
        self.connect("delete-event", self._on_delete_event)
        self.connect("key-press-event", self._on_key_press)


    # ----------------------------------------------------------------- UI -- #
    def _build_ui(self):
        # Assemble the whole window. A vertical Gtk.Box stacks menubar, toolbar,
        # the pane area, and the status bar; self.add() puts it in the window
        # (a Gtk.Window holds a single child). The four resizable panes are made
        # with nested Gtk.Paned splitters: each Paned has two children separated
        # by a draggable handle. pack1/pack2 are its left/right slots; resize
        # controls whether that side grows when the window resizes, shrink
        # whether it can be made smaller than its natural size. set_position sets
        # the initial handle offset in pixels.
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(vbox)

        vbox.pack_start(self._build_menubar(), False, False, 0)
        vbox.pack_start(self._build_toolbar(), False, False, 0)

        # Four-pane layout via nested GtkPaned: sidebar | (notelist | (editor |
        # outline)). The outline pane (pane 4) is hidden until toggled on.
        outer = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        inner = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        editor_split = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self._editor_split = editor_split

        outer.pack1(self._build_sidebar(), resize=False, shrink=False)
        outer.pack2(inner, resize=True, shrink=False)
        inner.pack1(self._build_notelist(), resize=False, shrink=False)
        inner.pack2(editor_split, resize=True, shrink=False)
        editor_split.pack1(self._build_editor(), resize=True, shrink=False)
        editor_split.pack2(self._build_outline(), resize=False, shrink=False)

        outer.set_position(200)
        inner.set_position(280)
        # Give the outline ~220px from the right when shown.
        editor_split.set_position(520)

        vbox.pack_start(outer, True, True, 0)
        vbox.pack_start(self._build_statusbar(), False, False, 0)


    # ----------------------------------------------------------- settings -- #
    def _apply_icon_set(self):
        """
        Apply a custom icon set from settings.icon_set_dir, if configured and
        valid:

          1. Set the running window/taskbar icon directly from the loaded
             pixbufs (immediate effect for this process).
          2. Install the files into the user's hicolor icon theme under the
             private name APP_ICON_NAME and rewrite the per-user .desktop file's
             Icon= line to match, so *other* launchers (panels, app menus) pick
             it up. The icon theme is then refreshed so the change is visible
             without a logout.

        When no/invalid set is configured, the installed theme icons and the
        desktop Icon= line are reverted to the stock "accessories-text-editor".
        Every step is best-effort and falls back silently to the stock icon.
        """
        files = icon_set_files(self.settings.icon_set_dir)
        if not files:
            # No custom set: revert to the stock icon everywhere.
            self.set_icon_name("accessories-text-editor")
            uninstall_icon_set(APP_ICON_NAME)
            update_desktop_icon("accessories-text-editor",
                                exec_path=self._script_path())
            self._refresh_icon_theme()
            return

        from gi.repository import GdkPixbuf
        pixbufs = []
        sources = []
        if "scalable" in files:
            sources.append(files["scalable"])
        for size in sorted(k for k in files if isinstance(k, int)):
            sources.append(files[size])
        for path in sources:
            try:
                pixbufs.append(GdkPixbuf.Pixbuf.new_from_file(path))
            except GLib.Error:
                continue  # skip an unreadable/invalid image

        # (2) Install into the theme + update the .desktop file so external
        # launchers resolve the icon by name.
        if install_icon_set(self.settings.icon_set_dir, APP_ICON_NAME):
            update_desktop_icon(APP_ICON_NAME,
                                exec_path=self._script_path())
            self._refresh_icon_theme()

        # (1) Immediate, in-process window icon.
        if pixbufs:
            try:
                self.set_icon_list(pixbufs)
                Gtk.Window.set_default_icon_list(pixbufs)
                return
            except (GLib.Error, TypeError):
                pass
        # If the pixbufs failed but the theme install succeeded, fall back to
        # the themed name; otherwise the stock icon.
        self.set_icon_name(APP_ICON_NAME)

    @staticmethod
    def _refresh_icon_theme():
        """Ask the default Gtk.IconTheme to rescan so freshly installed icons
        are visible without restarting the session."""
        try:
            Gtk.IconTheme.get_default().rescan_if_needed()
        except Exception:  # pragma: no cover - defensive
            pass

    @staticmethod
    def _script_path():
        """Absolute path to the entry-point script, for the .desktop Exec line."""
        import sys
        return os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else None

    def _restore_last_session(self):
        """
        Reopen the last workspace (if it still exists), restore the sidebar and
        note-list selection (panes 1 + 2), and reopen the notes that were open,
        one per tab. Invalid/missing entries are skipped. Used on startup when
        "restore session" is enabled and no folder was given on the CLI.
        """
        folder = self.settings.last_workspace
        if not folder or not os.path.isdir(folder):
            return
        self.open_folder(os.path.abspath(folder))

        # (#6) Restore the pane-1 sidebar selection, which reloads pane 2.
        node = self.settings.last_node
        if node in (NODE_ALL_NOTES, NODE_INBOX, NODE_EMPTY_NOTES,
                    NODE_SUBFOLDERS, NODE_SUBFOLDER):
            self._select_sidebar_node(node, self.settings.last_subfolder)

        # Reopen notes, one per tab. First replaces the initial empty tab.
        notes = [p for p in self.settings.last_open_notes
                 if isinstance(p, str) and os.path.isfile(p)]
        first = True
        for path in notes:
            if first:
                self._load_note_in_active_tab(model.Note(path))
                first = False
            else:
                self._load_note_in_new_tab(model.Note(path))
        if self._tabs:
            self.notebook.set_current_page(0)

        # (#6) Restore the pane-2 note-list selection (after the list reload).
        sel = self.settings.last_selected_note
        if sel and os.path.isfile(sel):
            self._reload_notelist(select_path=sel)

    def _apply_editor_font(self):
        """Apply the editor font from settings to every open tab."""
        for tab in self._tabs:
            tab.apply_font(self.settings.editor_font)

    def _apply_code_font(self):
        """Apply the code font from settings to every open tab."""
        for tab in self._tabs:
            tab.apply_code_font(self.settings.code_font)

    def _apply_preview_font(self):
        """Apply the markdown-preview body font from settings to every tab."""
        for tab in self._tabs:
            tab.apply_preview_font(self.settings.preview_font)

    def _apply_line_spacing(self):
        """Apply editor and preview line spacing from settings to every tab."""
        for tab in self._tabs:
            tab.apply_editor_line_spacing(self.settings.editor_line_spacing)
            tab.apply_preview_line_spacing(self.settings.preview_line_spacing)

    def _apply_tab_title_length(self):
        """Apply the configured tab-title length to every open tab."""
        for tab in self._tabs:
            tab.set_tab_title_length(self.settings.tab_title_length)


    # ------------------------------------------------------- read-only -- #
    def _apply_read_only(self):
        """Reflect self.read_only across all tabs and the status bar."""
        for tab in self._tabs:
            tab.set_editable(not self.read_only)
        self.update_status()

    def _set_read_only(self, value):
        """Single entry point: update state, both widgets, and apply."""
        self.read_only = bool(value)
        self._sync_toggle(self.btn_readonly, self.mi_readonly, self.read_only)
        self._apply_read_only()

    def on_toggle_read_only(self, button):
        # Toolbar button "toggled" handler. The guard flag is set while we mirror
        # state between the button and the menu item (in _sync_toggle), so we
        # ignore the echo it would otherwise cause. button.get_active() is the
        # new pressed state. The matching on_menu_* handler does the same for the
        # View-menu item; both funnel into the single _set_* entry point.
        if self._syncing_view_toggles:
            return
        self._set_read_only(button.get_active())

    def on_menu_toggle_read_only(self, item):
        # View-menu CheckMenuItem counterpart of on_toggle_read_only.
        if self._syncing_view_toggles:
            return
        self._set_read_only(item.get_active())


    # --------------------------------------------------------- preview -- #
    def _apply_preview(self):
        """Reflect self.preview_mode across all tabs and lock the read-only
        button while preview is active (preview is always read-only)."""
        for tab in self._tabs:
            tab.set_preview(self.preview_mode)
        # While previewing, the Read-only toggle is disabled (cannot change).
        self.btn_readonly.set_sensitive(not self.preview_mode)
        self.mi_readonly.set_sensitive(not self.preview_mode)
        self.update_status()
        # The outline jumps within the editor; refresh it for the new view.
        self._refresh_outline()

    def _set_preview(self, value):
        # Single entry point for the preview toggle: update state, mirror both
        # widgets (guarded), then apply across tabs.
        self.preview_mode = bool(value)
        self._sync_toggle(self.btn_preview, self.mi_preview, self.preview_mode)
        self._apply_preview()

    def on_toggle_preview(self, button):
        # Toolbar "toggled" handler (see on_toggle_read_only for the guard).
        if self._syncing_view_toggles:
            return
        self._set_preview(button.get_active())

    def on_menu_toggle_preview(self, item):
        # View-menu counterpart.
        if self._syncing_view_toggles:
            return
        self._set_preview(item.get_active())


    # ------------------------------------------------------- card view -- #
    def _set_card_view(self, value):
        self.card_view = bool(value)
        self._sync_toggle(self.btn_cardview, self.mi_cardview, self.card_view)
        self._apply_card_view()
        # Re-render the note list, keeping the current selection.
        tab = self._active_tab()
        keep = tab.note.path if (tab and tab.note) else None
        self._reload_notelist(select_path=keep)

    def on_toggle_card_view(self, button):
        # Toolbar "toggled" handler (see on_toggle_read_only for the guard).
        if self._syncing_view_toggles:
            return
        self._set_card_view(button.get_active())

    def on_menu_toggle_card_view(self, item):
        # View-menu counterpart.
        if self._syncing_view_toggles:
            return
        self._set_card_view(item.get_active())

    def _apply_card_view(self):
        """Show thin horizontal separator lines between cards in card view.
        set_grid_lines draws GTK's built-in tree grid lines (HORIZONTAL = lines
        between rows; NONE = none)."""
        lines = (Gtk.TreeViewGridLines.HORIZONTAL if self.card_view
                 else Gtk.TreeViewGridLines.NONE)
        self.note_view.set_grid_lines(lines)


    # --------------------------------------------------------- outline -- #
    def _set_outline(self, value):
        # Single entry point for the outline toggle: update state, mirror both
        # widgets (guarded), then show/hide + rebuild pane 4.
        self.outline_visible = bool(value)
        self._sync_toggle(self.btn_outline, self.mi_outline,
                          self.outline_visible)
        self._apply_outline_visibility()

    def on_toggle_outline(self, button):
        # Toolbar "toggled" handler (see on_toggle_read_only for the guard).
        if self._syncing_view_toggles:
            return
        self._set_outline(button.get_active())

    def on_menu_toggle_outline(self, item):
        # View-menu counterpart.
        if self._syncing_view_toggles:
            return
        self._set_outline(item.get_active())

    def _sync_toggle(self, button, menu_item, active):
        """Set a toolbar ToggleToolButton and a CheckMenuItem to `active`
        without re-firing their handlers (uses the window guard)."""
        self._syncing_view_toggles = True
        try:
            button.set_active(active)
            menu_item.set_active(active)
        finally:
            self._syncing_view_toggles = False


    # --------------------------------------------------------------- tabs -- #
    def _active_tab(self):
        # Map the notebook's current page index to our parallel _tabs list.
        # get_current_page returns -1 when there are no pages.
        idx = self.notebook.get_current_page()
        if idx < 0 or idx >= len(self._tabs):
            return None
        return self._tabs[idx]

    def _cycle_tab(self, forward=True):
        """Move to the next/previous tab, wrapping around."""
        n = len(self._tabs)
        if n <= 1:
            return
        cur = self.notebook.get_current_page()
        nxt = (cur + 1) % n if forward else (cur - 1) % n
        self.notebook.set_current_page(nxt)

    def _goto_tab(self, index):
        """Jump to tab `index` (0-based) if it exists."""
        if 0 <= index < len(self._tabs):
            self.notebook.set_current_page(index)

    def _on_key_press(self, _widget, event):
        """
        Tab navigation (#6):
          Ctrl+Tab           -> next tab
          Ctrl+Shift+Tab     -> previous tab
          Alt+1 .. Alt+9     -> jump to that tab
        Returns True to stop further handling when we act.
        """
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(event.state & Gdk.ModifierType.SHIFT_MASK)
        alt = bool(event.state & Gdk.ModifierType.MOD1_MASK)
        keyval = event.keyval

        # Ctrl+Tab / Ctrl+Shift+Tab. GTK also emits ISO_Left_Tab for shifted Tab.
        if ctrl and keyval in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab):
            self._cycle_tab(forward=not shift)
            return True

        # Alt+1 .. Alt+9 -> tab 0..8.
        if alt and Gdk.KEY_1 <= keyval <= Gdk.KEY_9:
            self._goto_tab(keyval - Gdk.KEY_1)
            return True

        return False

    def _new_tab(self, focus=True):
        """Create, append, and (optionally) switch to a new empty tab."""
        tab = EditorTab(on_changed=self._on_tab_changed,
                        on_close=self._close_tab,
                        code_font=self.settings.code_font,
                        tab_title_length=self.settings.tab_title_length,
                        on_context_menu=self._on_tab_context_menu)
        tab.apply_font(self.settings.editor_font)
        tab.apply_preview_font(self.settings.preview_font)
        tab.apply_editor_line_spacing(self.settings.editor_line_spacing)
        tab.apply_preview_line_spacing(self.settings.preview_line_spacing)
        tab.set_editable(not self.read_only)
        tab.set_preview(self.preview_mode)
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
        # Headings may have changed; refresh the outline if it's the active tab.
        if _tab is self._active_tab():
            self._refresh_outline()

    def _rebuild_recent_menu(self):
        """Repopulate the File > Open Recent submenu from settings.

        We empty the existing Gtk.Menu (remove each child), then add either a
        disabled "(none)" placeholder or one MenuItem per recent folder, binding
        the folder string as an extra arg to the activate handler. show_all makes
        the freshly added items visible.
        """
        for child in self.recent_menu.get_children():
            self.recent_menu.remove(child)

        recents = self.settings.recent_folders
        if not recents:
            placeholder = Gtk.MenuItem(label=Menu.RECENT_NONE)
            placeholder.set_sensitive(False)
            self.recent_menu.append(placeholder)
        else:
            for folder in recents:
                item = Gtk.MenuItem(label=folder)
                item.connect("activate", self.on_open_recent, folder)
                self.recent_menu.append(item)
        self.recent_menu.show_all()

    def _remember_folder(self, folder):
        """Record a folder as recent, persist, and refresh the menu. (settings
        does the dedupe/cap; no GTK beyond the menu rebuild.)"""
        self.settings.add_recent_folder(folder)
        self.settings.save()
        self._rebuild_recent_menu()


    # -------------------------------------------------------- status bar -- #
    def update_status(self):
        # Refresh the footer. The bold mode label uses Pango markup (<b>…</b>)
        # set via set_markup; the rest is plain text pushed onto the Gtk.Statusbar
        # (pop the previous message, push the new one — a statusbar is a stack).
        # Preview overrides the read-only/edit label.
        if self.preview_mode:
            self.mode_label.set_markup(f"<b>{Status.MODE_PREVIEW}</b>")
        elif self.read_only:
            self.mode_label.set_markup(f"<b>{Status.MODE_READ_ONLY}</b>")
        else:
            self.mode_label.set_markup(f"<b>{Status.MODE_EDIT}</b>")

        count = len(self.note_store)
        tab = self._active_tab()
        if tab and tab.note:
            sel = tab.note.display_name()
        else:
            sel = Status.SELECTED_NONE
        # When a search returns nothing, replace the item count with a notice.
        if self._search_no_results:
            msg = strings.status_no_results(sel)
        else:
            msg = strings.status_items(count, sel)
        if tab and tab.dirty:
            msg += "  *"
        if len(self._tabs) > 1:
            msg += strings.status_tab_position(
                self.notebook.get_current_page() + 1, len(self._tabs))
        self.statusbar.pop(self._status_ctx)
        self.statusbar.push(self._status_ctx, msg)
        self._update_slugify_sensitivity()
        self._update_save_sensitivity()

    def _update_save_sensitivity(self):
        """Enable Save only when the active tab has unsaved changes; enable
        Refresh whenever the active tab has a note open."""
        tab = self._active_tab()
        self.btn_save.set_sensitive(bool(tab and tab.note and tab.dirty))
        has_note = bool(tab and tab.note)
        self.btn_refresh.set_sensitive(has_note)
        # Mirror onto the File menu's Refresh note item.
        if hasattr(self, "mi_refresh"):
            self.mi_refresh.set_sensitive(has_note)

    def _update_slugify_sensitivity(self):
        """
        Enable Slugify only when NOT in read-only mode AND the active tab has a
        note whose current (live) first line is a short level-1 heading.
        """
        tab = self._active_tab()
        enabled = False
        if not self.read_only and tab is not None and tab.note is not None:
            heading = model.heading_for_slug(tab.get_content())
            enabled = heading is not None and model.slugify(heading) != ""
        self.btn_slugify.set_sensitive(enabled)


    # ------------------------------------------------------ folder logic -- #
    def open_folder(self, folder):
        # Switch the app to a new working folder: validate it, store it, retitle
        # the window (set_title updates the title bar), reset the sidebar
        # selection to All Notes, repopulate panes 1 and 2 from disk, clear the
        # active tab, and record the folder in the recent list.
        if not folder or not os.path.isdir(folder):
            self._error_dialog(strings.Dialog.not_a_folder(folder))
            return
        self.root_folder = folder
        self.set_title(f"{APP_NAME} \u2014 {folder}")
        self.current_node = NODE_ALL_NOTES
        self.current_subfolder = None
        self._reload_sidebar()
        self._reload_notelist()
        tab = self._active_tab()
        if tab:
            tab.clear()
        self.update_status()
        self._remember_folder(folder)

    def on_tab_switched(self, _notebook, _page, page_num):
        # Notebook "switch-page" handler: page_num is the newly active tab index.
        # GTK fires this during construction too; guard via _tabs presence.
        if getattr(self, "_tabs", None):
            if 0 <= page_num < len(self._tabs):
                self._tabs[page_num].highlight_search(self.search_query)
            self.update_status()
            self._refresh_outline()

    def on_new_tab(self, _widget):
        # Menu/Ctrl+T handler → open a fresh empty tab and focus it.
        self._new_tab(focus=True)

    def on_close_tab(self, _widget):
        # Menu/Ctrl+W handler → close the active tab (no-op at one tab; see
        # _close_tab).
        tab = self._active_tab()
        if tab is not None:
            self._close_tab(tab)
