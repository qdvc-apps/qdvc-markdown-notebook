"""
window.py — NotebookWindow: the view + controller for QDVC Markdown Notebook.

GTK and controller logic live together here, which is idiomatic for GTK (signal
handlers are wired directly to widgets). All filesystem and business logic is
delegated to qdvcmdnb_lib.model so this layer never touches disk directly.
"""

import os
from xml.sax.saxutils import escape as _xml_escape

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango, GLib  # noqa: E402

from . import model
from .config import (
    APP_NAME,
    SORT_ALPHA,
    SORT_DATE_NEW,
    SORT_DATE_OLD,
    ALL_NOTES,
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
from .editortab import EditorTab
from .preferences import PreferencesDialog


class NotebookWindow(Gtk.Window):

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

    def _build_menubar(self):
        menubar = Gtk.MenuBar()
        accel = Gtk.AccelGroup()
        self.add_accel_group(accel)
        self._accel_group = accel

        # ---- File menu ----
        file_menu = Gtk.Menu()
        file_item = Gtk.MenuItem.new_with_mnemonic("_File")
        file_item.set_submenu(file_menu)

        mi_new = self._icon_menu_item("New note", "document-new")
        mi_new.add_accelerator("activate", accel, Gdk.KEY_n,
                               Gdk.ModifierType.CONTROL_MASK,
                               Gtk.AccelFlags.VISIBLE)
        mi_new.connect("activate", self.on_new_note)
        file_menu.append(mi_new)

        mi_save = self._icon_menu_item("Save note", "document-save")
        mi_save.add_accelerator("activate", accel, Gdk.KEY_s,
                                Gdk.ModifierType.CONTROL_MASK,
                                Gtk.AccelFlags.VISIBLE)
        mi_save.connect("activate", self.on_save_note)
        file_menu.append(mi_save)

        # Refresh note — mirrors the toolbar button; Ctrl+R. Disabled until a
        # note is open (kept in sync in _update_save_sensitivity).
        self.mi_refresh = self._icon_menu_item("Refresh note", "view-refresh")
        self.mi_refresh.add_accelerator("activate", accel, Gdk.KEY_r,
                                        Gdk.ModifierType.CONTROL_MASK,
                                        Gtk.AccelFlags.VISIBLE)
        self.mi_refresh.set_sensitive(False)
        self.mi_refresh.connect("activate", self.on_refresh_note)
        file_menu.append(self.mi_refresh)

        file_menu.append(Gtk.SeparatorMenuItem())

        mi_open = self._icon_menu_item("Open workspace", "folder-open")
        mi_open.add_accelerator("activate", accel, Gdk.KEY_o,
                                Gdk.ModifierType.CONTROL_MASK,
                                Gtk.AccelFlags.VISIBLE)
        mi_open.connect("activate", self.on_open_folder)
        file_menu.append(mi_open)

        # Refresh workspace — re-scan the working folder and rebuild panes 1+2
        # from disk. Same icon as Refresh note. Ctrl+Shift+R.
        self.mi_refresh_ws = self._icon_menu_item("Refresh workspace",
                                                  "view-refresh")
        self.mi_refresh_ws.add_accelerator(
            "activate", accel, Gdk.KEY_r,
            Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK,
            Gtk.AccelFlags.VISIBLE)
        self.mi_refresh_ws.connect("activate", self.on_refresh_workspace)
        file_menu.append(self.mi_refresh_ws)

        mi_close_ws = Gtk.MenuItem(label="Close workspace")
        mi_close_ws.connect("activate", self.on_close_workspace)
        file_menu.append(mi_close_ws)

        # "Open recent workspace" submenu, populated dynamically from settings.
        self.recent_menu_item = self._icon_menu_item(
            "Open recent workspace", "document-open-recent")
        self.recent_menu = Gtk.Menu()
        self.recent_menu_item.set_submenu(self.recent_menu)
        file_menu.append(self.recent_menu_item)

        file_menu.append(Gtk.SeparatorMenuItem())

        mi_new_tab = self._icon_menu_item("New tab", "tab-new")
        mi_new_tab.add_accelerator("activate", accel, Gdk.KEY_t,
                                   Gdk.ModifierType.CONTROL_MASK,
                                   Gtk.AccelFlags.VISIBLE)
        mi_new_tab.connect("activate", self.on_new_tab)
        file_menu.append(mi_new_tab)

        mi_close_tab = Gtk.MenuItem(label="Close tab")
        mi_close_tab.add_accelerator("activate", accel, Gdk.KEY_w,
                                     Gdk.ModifierType.CONTROL_MASK,
                                     Gtk.AccelFlags.VISIBLE)
        mi_close_tab.connect("activate", self.on_close_tab)
        file_menu.append(mi_close_tab)

        file_menu.append(Gtk.SeparatorMenuItem())

        mi_quit = self._icon_menu_item("Quit", "application-exit")
        # Note: the spec listed Ctrl+S for Quit; that collides with Save,
        # so Quit is bound to the conventional Ctrl+Q instead. See MAINTENANCE.md.
        mi_quit.add_accelerator("activate", accel, Gdk.KEY_q,
                                Gdk.ModifierType.CONTROL_MASK,
                                Gtk.AccelFlags.VISIBLE)
        mi_quit.connect("activate", self.on_quit)
        file_menu.append(mi_quit)

        menubar.append(file_item)

        # ---- Edit menu ----
        edit_menu = Gtk.Menu()
        edit_item = Gtk.MenuItem.new_with_mnemonic("_Edit")
        edit_item.set_submenu(edit_menu)

        mi_prefs = self._icon_menu_item("Preferences\u2026", "preferences-system")
        mi_prefs.connect("activate", self.on_preferences)
        edit_menu.append(mi_prefs)

        menubar.append(edit_item)

        # ---- View menu ----
        view_menu = Gtk.Menu()
        view_item = Gtk.MenuItem.new_with_mnemonic("_View")
        view_item.set_submenu(view_menu)

        self.mi_toolbar = Gtk.CheckMenuItem(label="Toolbar")
        self.mi_toolbar.set_active(True)
        self.mi_toolbar.connect("toggled", self.on_toggle_toolbar)
        view_menu.append(self.mi_toolbar)

        self.mi_statusbar = Gtk.CheckMenuItem(label="Statusbar")
        self.mi_statusbar.set_active(True)
        self.mi_statusbar.connect("toggled", self.on_toggle_statusbar)
        view_menu.append(self.mi_statusbar)

        view_menu.append(Gtk.SeparatorMenuItem())

        # Mode toggles that mirror the toolbar's toggle buttons. A guard flag
        # (_syncing_view_toggles) prevents the menu↔toolbar sync from looping.
        self._syncing_view_toggles = False

        self.mi_readonly = Gtk.CheckMenuItem(label="Read-only")
        self.mi_readonly.set_active(True)
        self.mi_readonly.add_accelerator("activate", accel, Gdk.KEY_e,
                                         Gdk.ModifierType.CONTROL_MASK,
                                         Gtk.AccelFlags.VISIBLE)
        self.mi_readonly.connect("toggled", self.on_menu_toggle_read_only)
        view_menu.append(self.mi_readonly)

        self.mi_cardview = Gtk.CheckMenuItem(label="Card view")
        self.mi_cardview.add_accelerator("activate", accel, Gdk.KEY_d,
                                         Gdk.ModifierType.CONTROL_MASK,
                                         Gtk.AccelFlags.VISIBLE)
        self.mi_cardview.connect("toggled", self.on_menu_toggle_card_view)
        view_menu.append(self.mi_cardview)

        self.mi_preview = Gtk.CheckMenuItem(label="Preview")
        self.mi_preview.add_accelerator("activate", accel, Gdk.KEY_grave,
                                        Gdk.ModifierType.CONTROL_MASK,
                                        Gtk.AccelFlags.VISIBLE)
        self.mi_preview.connect("toggled", self.on_menu_toggle_preview)
        view_menu.append(self.mi_preview)

        self.mi_outline = Gtk.CheckMenuItem(label="Headings outline")
        self.mi_outline.add_accelerator("activate", accel, Gdk.KEY_o,
                                        Gdk.ModifierType.CONTROL_MASK
                                        | Gdk.ModifierType.SHIFT_MASK,
                                        Gtk.AccelFlags.VISIBLE)
        self.mi_outline.connect("toggled", self.on_menu_toggle_outline)
        view_menu.append(self.mi_outline)

        view_menu.append(Gtk.SeparatorMenuItem())

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

        # Keep references so a restored/persisted sort mode can be reflected.
        self._sort_items = {
            SORT_ALPHA: mi_alpha,
            SORT_DATE_NEW: mi_new_first,
            SORT_DATE_OLD: mi_old_first,
        }

        menubar.append(view_item)

        # ---- Help menu ----
        help_menu = Gtk.Menu()
        help_item = Gtk.MenuItem.new_with_mnemonic("_Help")
        help_item.set_submenu(help_menu)

        mi_about = self._icon_menu_item("About", "help-about")
        mi_about.connect("activate", self.on_about)
        help_menu.append(mi_about)

        menubar.append(help_item)
        return menubar

    @staticmethod
    def _icon_menu_item(label, icon_name):
        """
        Build a menu item with a leading icon, GNOME2/MATE style.

        Uses Gtk.ImageMenuItem (deprecated in GTK3 but the idiomatic way to get
        icons in menus, and a good fit for this app's MATE-era look). Falls back
        to a plain MenuItem if ImageMenuItem is unavailable.
        """
        try:
            item = Gtk.ImageMenuItem(label=label)
            img = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.MENU)
            item.set_image(img)
            item.set_always_show_image(True)
            return item
        except (AttributeError, TypeError):
            return Gtk.MenuItem(label=label)

    def _toolbar_style_enum(self):
        from .settings import TOOLBAR_TEXT_BESIDE
        if self.settings.toolbar_style == TOOLBAR_TEXT_BESIDE:
            return Gtk.ToolbarStyle.BOTH_HORIZ
        return Gtk.ToolbarStyle.BOTH

    def _build_toolbar(self):
        toolbar = Gtk.Toolbar()
        self.toolbar = toolbar
        toolbar.set_style(self._toolbar_style_enum())

        btn_new = Gtk.ToolButton(icon_name="document-new")
        btn_new.set_label("New note")
        btn_new.set_tooltip_text("Create a new note in the selected folder")
        btn_new.connect("clicked", self.on_new_note)
        toolbar.insert(btn_new, -1)

        self.btn_save = Gtk.ToolButton(icon_name="document-save")
        self.btn_save.set_label("Save note")
        self.btn_save.set_tooltip_text("Save the current note")
        self.btn_save.set_sensitive(False)  # enabled only when dirty
        self.btn_save.connect("clicked", self.on_save_note)
        toolbar.insert(self.btn_save, -1)

        # Refresh note: reload the current note from disk (e.g. edited elsewhere).
        self.btn_refresh = Gtk.ToolButton(icon_name="view-refresh")
        self.btn_refresh.set_label("Refresh note")
        self.btn_refresh.set_tooltip_text(
            "Reload the current note from disk")
        self.btn_refresh.set_sensitive(False)  # enabled only with a note open
        self.btn_refresh.connect("clicked", self.on_refresh_note)
        toolbar.insert(self.btn_refresh, -1)

        # Slugify: rename the active note from its level-1 heading. Enabled only
        # when the active tab's first line is a short (<32 char) H1.
        self.btn_slugify = Gtk.ToolButton(icon_name="insert-link")
        self.btn_slugify.set_label("Slugify")
        self.btn_slugify.set_tooltip_text(
            "Rename this note from its level-1 heading")
        self.btn_slugify.set_sensitive(False)
        self.btn_slugify.connect("clicked", self.on_slugify)
        toolbar.insert(self.btn_slugify, -1)

        toolbar.insert(self._toolbar_separator(), -1)

        # Card view toggle: when active, pane 2 shows each note as a small card
        # (bold title + date + first body line). Off by default.
        self.btn_cardview = Gtk.ToggleToolButton()
        self.btn_cardview.set_icon_name("mail-attachment")
        self.btn_cardview.set_label("Card view")
        self.btn_cardview.set_tooltip_text(
            "Show notes as cards (title, date, first line)")
        self.btn_cardview.set_active(False)
        # "Important" items keep their label beside the icon in BOTH_HORIZ mode.
        self.btn_cardview.set_is_important(True)
        self.btn_cardview.connect("toggled", self.on_toggle_card_view)
        toolbar.insert(self.btn_cardview, -1)

        toolbar.insert(self._toolbar_separator(), -1)

        # Read-only toggle. Pressed-in (active) means read-only; releasing it
        # enters edit mode. Applies across all tabs.
        self.btn_readonly = Gtk.ToggleToolButton()
        self.btn_readonly.set_icon_name("changes-prevent-symbolic")
        self.btn_readonly.set_label("Read-only")
        self.btn_readonly.set_tooltip_text(
            "Read-only mode (release to edit)")
        self.btn_readonly.set_active(True)  # default: read-only
        self.btn_readonly.set_is_important(True)
        self._readonly_handler = self.btn_readonly.connect(
            "toggled", self.on_toggle_read_only)
        toolbar.insert(self.btn_readonly, -1)

        # Preview toggle: when active, all tabs show rendered markdown (read-only)
        # and the Read-only button is disabled. Applies across all tabs.
        self.btn_preview = Gtk.ToggleToolButton()
        self.btn_preview.set_icon_name("document-page-setup")
        self.btn_preview.set_label("Preview")
        self.btn_preview.set_tooltip_text(
            "Preview rendered markdown (read-only)")
        self.btn_preview.set_active(False)
        self.btn_preview.set_is_important(True)
        self.btn_preview.connect("toggled", self.on_toggle_preview)
        toolbar.insert(self.btn_preview, -1)

        # Outline toggle: show/hide the headings-outline pane (pane 4).
        self.btn_outline = Gtk.ToggleToolButton()
        self.btn_outline.set_icon_name("view-list")
        self.btn_outline.set_label("Outline")
        self.btn_outline.set_tooltip_text(
            "Show the headings outline of the current note")
        self.btn_outline.set_active(False)
        self.btn_outline.set_is_important(True)
        self.btn_outline.connect("toggled", self.on_toggle_outline)
        toolbar.insert(self.btn_outline, -1)

        return toolbar

    @staticmethod
    def _toolbar_separator():
        sep = Gtk.SeparatorToolItem()
        sep.set_draw(True)  # ensure the divider line is actually drawn
        return sep

    def _apply_toolbar_style(self):
        self.toolbar.set_style(self._toolbar_style_enum())

    def _build_sidebar(self):
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        # Columns: icon name (str), display label (str), node kind (str),
        #          subfolder name (str, only meaningful for NODE_SUBFOLDER)
        self.sidebar_store = Gtk.TreeStore(str, str, str, str)
        self.sidebar_view = Gtk.TreeView(model=self.sidebar_store)
        self.sidebar_view.set_headers_visible(False)

        col = Gtk.TreeViewColumn("Folders")
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
        # Vertical box: a search row on top, then the list/placeholder stack.
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # --- search row ---
        search_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        search_row.set_margin_start(4)
        search_row.set_margin_end(4)
        search_row.set_margin_top(4)
        search_row.set_margin_bottom(4)

        self.search_entry = Gtk.Entry()
        self.search_entry.set_placeholder_text("Search notes\u2026")
        self.search_entry.set_hexpand(True)
        # Only search on ENTER (the "activate" signal), not on every keystroke.
        self.search_entry.connect("activate", self.on_search)
        # A clear icon inside the entry; clearing resets the filter.
        self.search_entry.set_icon_from_icon_name(
            Gtk.EntryIconPosition.SECONDARY, "edit-clear-symbolic")
        self.search_entry.connect("icon-press", self.on_search_icon_press)
        search_row.pack_start(self.search_entry, True, True, 0)

        search_btn = Gtk.Button(label="Search")
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
        col = Gtk.TreeViewColumn("Notes", renderer)
        col.set_cell_data_func(renderer, self._note_cell_data)
        self.note_view.append_column(col)

        self.note_view.get_selection().connect(
            "changed", self.on_note_selection_changed)
        self.note_view.connect("button-press-event",
                               self.on_notelist_button_press)

        scroll.add(self.note_view)
        self.notelist_stack.add_named(scroll, "list")
        self.notelist_stack.add_named(
            self._make_placeholder("Select a folder or note"), "placeholder")
        self.notelist_stack.set_visible_child_name("list")
        outer.pack_start(self.notelist_stack, True, True, 0)
        return outer

    @staticmethod
    def _make_placeholder(text):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_valign(Gtk.Align.CENTER)
        box.set_halign(Gtk.Align.CENTER)
        label = Gtk.Label()
        label.set_markup(
            f"<span size='large' foreground='#888888'>{text}</span>")
        box.add(label)
        return box

    def _show_notelist_placeholder(self):
        self.note_store.clear()
        self.notelist_stack.set_visible_child_name("placeholder")
        self.update_status()

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

    def _build_outline(self):
        """
        Pane 4: a tree of the current note's markdown headings. Each row stores
        the heading title and the 0-based source line to jump to. Hidden until
        toggled on (the toggle calls _apply_outline_visibility).
        """
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.outline_scroll = scroll

        # Columns: display label (str), source line index (int).
        self.outline_store = Gtk.TreeStore(str, int)
        self.outline_view = Gtk.TreeView(model=self.outline_store)
        self.outline_view.set_headers_visible(False)
        col = Gtk.TreeViewColumn("Outline", Gtk.CellRendererText(), text=0)
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
        # A horizontal strip: a bold mode indicator (#1) on the left, then the
        # regular statusbar filling the rest.
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
        if self._syncing_view_toggles:
            return
        self._set_read_only(button.get_active())

    def on_menu_toggle_read_only(self, item):
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
        self.preview_mode = bool(value)
        self._sync_toggle(self.btn_preview, self.mi_preview, self.preview_mode)
        self._apply_preview()

    def on_toggle_preview(self, button):
        if self._syncing_view_toggles:
            return
        self._set_preview(button.get_active())

    def on_menu_toggle_preview(self, item):
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
        if self._syncing_view_toggles:
            return
        self._set_card_view(button.get_active())

    def on_menu_toggle_card_view(self, item):
        if self._syncing_view_toggles:
            return
        self._set_card_view(item.get_active())

    def _apply_card_view(self):
        """Show thin horizontal separator lines between cards in card view."""
        lines = (Gtk.TreeViewGridLines.HORIZONTAL if self.card_view
                 else Gtk.TreeViewGridLines.NONE)
        self.note_view.set_grid_lines(lines)

    # --------------------------------------------------------- outline -- #
    def _set_outline(self, value):
        self.outline_visible = bool(value)
        self._sync_toggle(self.btn_outline, self.mi_outline,
                          self.outline_visible)
        self._apply_outline_visibility()

    def on_toggle_outline(self, button):
        if self._syncing_view_toggles:
            return
        self._set_outline(button.get_active())

    def on_menu_toggle_outline(self, item):
        if self._syncing_view_toggles:
            return
        self._set_outline(item.get_active())

    def _apply_outline_visibility(self):
        """Show/hide the outline pane and (re)build it when shown."""
        if self.outline_visible:
            self.outline_scroll.show()
            self.outline_view.show_all()
            self._refresh_outline()
        else:
            self.outline_scroll.hide()

    def _refresh_outline(self):
        """Rebuild the outline tree from the active tab's current content."""
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

    def on_outline_row_activated(self, _view, path, _col):
        treeiter = self.outline_store.get_iter(path)
        self._jump_to_outline_line(self.outline_store[treeiter][1])

    def on_outline_selection_changed(self, selection):
        if self._outline_guard:
            return
        _model, treeiter = selection.get_selected()
        if treeiter is None:
            return
        self._jump_to_outline_line(_model[treeiter][1])

    def _jump_to_outline_line(self, line_index):
        tab = self._active_tab()
        if tab is not None and tab.note is not None:
            tab.scroll_to_line(line_index)

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
        # Bold mode indicator. Preview overrides the read-only/edit label.
        if self.preview_mode:
            self.mode_label.set_markup("<b>Rendered Markdown preview</b>")
        elif self.read_only:
            self.mode_label.set_markup("<b>Read-only mode</b>")
        else:
            self.mode_label.set_markup("<b>Edit mode</b>")

        count = len(self.note_store)
        tab = self._active_tab()
        if tab and tab.note:
            sel = tab.note.display_name()
        else:
            sel = "none"
        # When a search returns nothing, replace the item count with a notice.
        if self._search_no_results:
            msg = f"No search results found!  |  Selected: {sel}"
        else:
            msg = f"{count} item(s)  |  Selected: {sel}"
        if tab and tab.dirty:
            msg += "  *"
        if len(self._tabs) > 1:
            msg += f"  |  Tab {self.notebook.get_current_page() + 1}" \
                   f"/{len(self._tabs)}"
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
        if not folder or not os.path.isdir(folder):
            self._error_dialog(f"Not a folder:\n{folder}")
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

    def on_refresh_workspace(self, _widget):
        """
        Re-scan the working folder from disk and rebuild panes 1 and 2, keeping
        the current sidebar selection (and the pane-2 note selection) where
        possible. Open tabs are left untouched. No-op without a workspace.
        """
        if not self.root_folder:
            self._error_dialog("Open a working folder first (Ctrl+O).")
            return
        if not os.path.isdir(self.root_folder):
            self._error_dialog(
                f"Working folder no longer exists:\n{self.root_folder}")
            return
        # Preserve the pane-2 selection by path across the rebuild.
        sel = self.note_view.get_selection()
        _m, it = sel.get_selected()
        keep = self.note_store[it][1] if it is not None else None
        # Rebuilding the sidebar with preserve_selection reloads pane 2 via the
        # selection handler; then restore the note selection.
        self._reload_sidebar(preserve_selection=True)
        self._reload_notelist(select_path=keep)
        self.update_status()

    def on_close_workspace(self, _widget):
        """Close the current workspace, returning to the empty initial state."""
        if self._confirm_close_all() is False:
            return
        self.root_folder = None
        self.current_node = NODE_ALL_NOTES
        self.current_subfolder = None
        self.search_query = None
        self._search_no_results = False
        self.search_entry.set_text("")
        self.set_title(APP_NAME)
        self.sidebar_store.clear()
        self.note_store.clear()
        self.notelist_stack.set_visible_child_name("list")
        for tab in self._tabs:
            tab.clear()
        self.update_status()

    # ------------------------------------------------------- view toggles -- #
    def on_toggle_toolbar(self, item):
        self.toolbar.set_visible(item.get_active())

    def on_toggle_statusbar(self, item):
        self.statusbar_box.set_visible(item.get_active())

    # ------------------------------------------------------------ search -- #
    def on_search(self, _widget):
        """Run the search from the entry's current text (ENTER or button)."""
        text = self.search_entry.get_text().strip()
        # An empty box means no filter.
        self.search_query = text or None
        self._reload_notelist()
        self._apply_search_highlight()

    def on_search_icon_press(self, entry, icon_pos, _event):
        """Clear icon pressed: empty the box and drop the filter."""
        if icon_pos == Gtk.EntryIconPosition.SECONDARY:
            entry.set_text("")
            self.search_query = None
            self._reload_notelist()
            self._apply_search_highlight()

    def _apply_search_highlight(self):
        """(#5) Highlight the current search term in the active tab's document.
        A cleared search removes the highlight."""
        tab = self._active_tab()
        if tab is not None:
            tab.highlight_search(self.search_query)

    def _reload_sidebar(self, preserve_selection=False):
        # Remember the current selection so a refresh doesn't reset it.
        prev_node = self.current_node
        prev_sub = self.current_subfolder

        self.sidebar_store.clear()
        # Row schema: [icon_name, label, node_kind, subfolder_name]
        self.sidebar_store.append(
            None, ["emblem-documents", "All Notes", NODE_ALL_NOTES, ""])
        # Inbox: notes sitting at the top level (not yet filed into a subfolder).
        self.sidebar_store.append(
            None, ["mail-inbox", "Inbox", NODE_INBOX, ""])
        self.sidebar_store.append(
            None, ["edit-clear", "Empty Notes", NODE_EMPTY_NOTES, ""])

        subfolders_iter = self.sidebar_store.append(
            None, ["folder", "Subfolders", NODE_SUBFOLDERS, ""])
        if self.root_folder:
            for sub in model.immediate_subfolders(self.root_folder):
                self.sidebar_store.append(
                    subfolders_iter, ["folder", sub, NODE_SUBFOLDER, sub])

        # Expand the Subfolders branch so its children are visible.
        self.sidebar_view.expand_all()

        if preserve_selection and prev_node is not None:
            # Restore the prior selection if it still exists; else fall back to
            # All Notes. _select_sidebar_node reloads pane 2 via its handler.
            if not self._select_sidebar_node(prev_node, prev_sub):
                self.sidebar_view.get_selection().select_path(
                    Gtk.TreePath.new_first())
        else:
            # Default: select "All Notes".
            self.sidebar_view.get_selection().select_path(
                Gtk.TreePath.new_first())

    def _notes_for_current_subfolder(self):
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
        Build the cell markup at draw time. In list view it's just the title.
        In card view it's three lines: bold title, then the last-modified date
        and the first body line. The sub-lines use the same colour as the title
        (so nothing clashes with the selection highlight) but are italicised and
        slightly smaller to set them apart. Card rows also get a little extra
        top/bottom padding.
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

    # ----------------------------------------------------------- editor -- #
    def _load_note_in_active_tab(self, note):
        tab = self._active_tab()
        if tab is None:
            tab = self._new_tab(focus=True)
        if not tab.load_note(note):
            self._error_dialog(f"Could not open note:\n{note.path}")
            return
        tab.highlight_search(self.search_query)
        self.update_status()
        self._refresh_outline()

    def _load_note_in_new_tab(self, note):
        tab = self._new_tab(focus=True)
        if not tab.load_note(note):
            self._error_dialog(f"Could not open note:\n{note.path}")
            return
        tab.highlight_search(self.search_query)
        self.update_status()
        self._refresh_outline()

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
        node_kind = model_[treeiter][2]
        self.current_node = node_kind
        if node_kind == NODE_SUBFOLDER:
            self.current_subfolder = model_[treeiter][3]
        else:
            self.current_subfolder = None

        if node_kind == NODE_SUBFOLDERS:
            # The "Subfolders" parent itself has no note list: show placeholders
            # in both the note list (pane 2) and the editor (pane 3).
            self._show_notelist_placeholder()
            tab = self._active_tab()
            if tab:
                tab.clear()
        else:
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
        # Right-click (button 3) opens the context menu on the row under it,
        # WITHOUT changing the current selection (so right-clicking doesn't open
        # the note in the active tab).
        if event.button != 3:
            return False
        path_info = self.note_view.get_path_at_pos(int(event.x), int(event.y))
        if path_info is None:
            return False
        path, _col, _cx, _cy = path_info
        treeiter = self.note_store.get_iter(path)
        note_path = self.note_store[treeiter][1]

        menu = self._build_note_context_menu(note_path, include_locate=False)
        menu.popup_at_pointer(event)
        return True

    def _on_tab_context_menu(self, tab, event):
        """
        Right-click on a tab label: show the same context menu as a pane-2
        right-click, plus a "Locate in subfolders" item at the top. No-op for a
        tab with no note open (guarded in EditorTab).
        """
        if tab.note is None:
            return
        menu = self._build_note_context_menu(
            tab.note.path, include_locate=True, tab=tab)
        menu.popup_at_pointer(event)

    def _build_note_context_menu(self, note_path, include_locate=False,
                                 tab=None):
        """
        Build the shared context menu for a note (used by both pane-2 right-click
        and tab right-click). Several items carry leading icons. When
        `include_locate` is True an extra "Locate in subfolders" item is added at
        the top (used from a tab, where `tab` is that EditorTab) which reveals
        the note in panes 1 and 2.
        """
        menu = Gtk.Menu()

        if include_locate:
            item_locate = self._icon_menu_item("Locate in subfolders",
                                                "edit-find")
            item_locate.connect(
                "activate",
                lambda _i: self._locate_note_in_panes(note_path))
            menu.append(item_locate)
            menu.append(Gtk.SeparatorMenuItem())

        item_open = self._icon_menu_item("Open in new tab", "tab-new")
        item_open.connect(
            "activate",
            lambda _i: self._load_note_in_new_tab(model.Note(note_path)))
        menu.append(item_open)

        # "Move to subfolder" → a submenu listing every subfolder of the
        # workspace (plus the top level). Confirms before moving.
        item_move = self._icon_menu_item("Move to subfolder", "folder-move")
        item_move.set_submenu(self._build_move_submenu(note_path, tab))
        # Only meaningful with a workspace open.
        item_move.set_sensitive(bool(self.root_folder))
        menu.append(item_move)

        menu.append(Gtk.SeparatorMenuItem())

        item_copy = self._icon_menu_item("Copy full path", "edit-copy")
        item_copy.connect("activate",
                          lambda _i: self._copy_path_to_clipboard(note_path))
        menu.append(item_copy)

        item_browse = self._icon_menu_item("Show in file browser",
                                           "system-file-manager")
        item_browse.connect("activate",
                            lambda _i: self._show_in_file_browser(note_path))
        menu.append(item_browse)

        menu.show_all()
        return menu

    def _build_move_submenu(self, note_path, tab):
        """Submenu of destination subfolders for "Move to subfolder"."""
        submenu = Gtk.Menu()
        if not self.root_folder:
            mi = Gtk.MenuItem(label="(open a workspace first)")
            mi.set_sensitive(False)
            submenu.append(mi)
            submenu.show_all()
            return submenu

        cur_dir = os.path.abspath(os.path.dirname(note_path))
        for rel in model.all_subfolders(self.root_folder):
            dest = (self.root_folder if rel == ""
                    else os.path.join(self.root_folder, rel))
            label = "(top level)" if rel == "" else rel
            mi = Gtk.MenuItem(label=label)
            # Disable the folder the note already lives in.
            if os.path.abspath(dest) == cur_dir:
                mi.set_sensitive(False)
            else:
                mi.connect(
                    "activate",
                    lambda _i, d=dest, lbl=label: self._move_note_to(
                        note_path, d, lbl, tab))
            submenu.append(mi)
        submenu.show_all()
        return submenu

    def _move_note_to(self, note_path, dest_folder, label, tab):
        """Confirm, then move the note into `dest_folder` and refresh UI."""
        name = os.path.basename(note_path)
        if not self._confirm(
                "Move this note?",
                f"\u201c{name}\u201d will be moved to \u201c{label}\u201d."):
            return
        # Find every open tab that points at this note (by old path) so we can
        # update them to the new location after the move. Comparing by path
        # rather than object identity is important: a tab may hold its own
        # throwaway Note for the same file.
        old_abs = os.path.abspath(note_path)
        owning_tabs = [t for t in self._tabs
                       if t.note is not None
                       and os.path.abspath(t.note.path) == old_abs]

        # Move on disk via a single Note (reused by the first owning tab if any,
        # so its in-place path/name update is reflected there too).
        note = owning_tabs[0].note if owning_tabs else model.Note(note_path)
        try:
            new_path = model.move_note(note, dest_folder)
        except OSError as exc:
            self._error_dialog(f"Could not move note:\n{exc}")
            return

        # Point every owning tab at the new path and refresh its title. The
        # buffer content is unchanged by a move, so we don't reload from disk
        # (which also avoids any read at the now-nonexistent old path).
        for t in owning_tabs:
            t.note.path = new_path
            t.note.name = os.path.basename(new_path)
            t._refresh_title()

        # Rebuild panes. Guard the note-list reselection so it does not trigger
        # a reload of the active tab (which could otherwise read a stale path).
        self._reload_sidebar()
        self._note_select_guard = True
        try:
            self._reload_notelist(select_path=new_path)
        finally:
            self._note_select_guard = False
        self.update_status()
        self._refresh_outline()

    def _locate_note_in_panes(self, note_path):
        """
        Reveal `note_path` in the sidebar (pane 1) and note list (pane 2):
        select the subfolder that contains it (or All Notes if it sits at the
        workspace root or outside any immediate subfolder), then select the row.
        """
        if not self.root_folder:
            return
        note_dir = os.path.abspath(os.path.dirname(note_path))
        root = os.path.abspath(self.root_folder)
        # Determine the immediate subfolder (first path component under root)
        # that contains the note, if any.
        target_node = NODE_ALL_NOTES
        target_sub = None
        try:
            rel = os.path.relpath(note_dir, root)
        except ValueError:
            rel = ""
        if rel and not rel.startswith(".."):
            first = rel.split(os.sep)[0]
            if first and first != ".":
                target_sub = first
                target_node = NODE_SUBFOLDER

        # Select the matching sidebar row (which reloads the note list via its
        # selection handler), then select the note row in pane 2.
        self._select_sidebar_node(target_node, target_sub)
        self._reload_notelist(select_path=note_path)

    def _select_sidebar_node(self, node_kind, subfolder=None):
        """
        Programmatically select a sidebar row by kind (and subfolder name).
        Returns True if a matching row was found and selected, else False.
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

    def _copy_path_to_clipboard(self, path):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(path, -1)
        clipboard.store()

    def _show_in_file_browser(self, path):
        """Open the file's containing folder in the default file manager."""
        folder = os.path.dirname(path)
        uri = GLib.filename_to_uri(folder, None)
        try:
            Gtk.show_uri_on_window(self, uri, Gdk.CURRENT_TIME)
        except GLib.Error as exc:
            self._error_dialog(f"Could not open file browser:\n{exc}")

    def on_tab_switched(self, _notebook, _page, page_num):
        # GTK fires this during construction too; guard via _tabs presence.
        if getattr(self, "_tabs", None):
            if 0 <= page_num < len(self._tabs):
                self._tabs[page_num].highlight_search(self.search_query)
            self.update_status()
            self._refresh_outline()

    def on_new_tab(self, _widget):
        self._new_tab(focus=True)

    def on_close_tab(self, _widget):
        tab = self._active_tab()
        if tab is not None:
            self._close_tab(tab)

    def on_new_note(self, _widget):
        if self.read_only:
            self._error_dialog(
                "Read-only mode is on. Release the Read-only button to make "
                "changes.")
            return
        if not self.root_folder:
            self._error_dialog("Open a working folder first (Ctrl+O).")
            return
        # Target folder = the selected subfolder if one is selected, else root.
        if self.current_node == NODE_SUBFOLDER and self.current_subfolder:
            target_dir = os.path.join(self.root_folder, self.current_subfolder)
        else:
            target_dir = self.root_folder

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

    def on_refresh_note(self, _widget):
        """Reload the active tab's note from disk (e.g. changed elsewhere).
        If the tab has unsaved changes, warn first (same prompt as closing)."""
        tab = self._active_tab()
        if tab is None or tab.note is None:
            return
        if self._maybe_warn_unsaved(tab) is False:
            return  # user cancelled
        note = model.Note(tab.note.path)
        if not tab.load_note(note):
            self._error_dialog(f"Could not reload note:\n{note.path}")
            return
        tab.highlight_search(self.search_query)
        self.update_status()

    def on_slugify(self, _widget):
        tab = self._active_tab()
        if tab is None or tab.note is None:
            return
        heading = model.heading_for_slug(tab.get_content())
        if heading is None:
            return
        slug = model.slugify(heading)
        if not slug:
            return

        old_name = tab.note.name
        new_name = slug + ".md"
        if not self._confirm(
                "Rename this note?",
                f"\u201c{old_name}\u201d will be renamed to \u201c{new_name}\u201d."):
            return

        try:
            new_path = model.rename_note(tab.note, slug)
        except OSError as exc:
            self._error_dialog(f"Could not rename note:\n{exc}")
            return
        # tab.note was updated in place by rename_note; refresh title + list.
        tab._refresh_title()
        self._reload_notelist(select_path=new_path)
        self.update_status()

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

    def on_preferences(self, _widget):
        dialog = PreferencesDialog(self, self.settings,
                                   on_apply=self._apply_preferences)
        dialog.run_modal()

    def _apply_preferences(self):
        """Re-theme tabs and toolbar after a preferences change."""
        self._apply_editor_font()
        self._apply_code_font()
        self._apply_preview_font()
        self._apply_line_spacing()
        self._apply_toolbar_style()
        self._apply_tab_title_length()
        self._apply_icon_set()

    def on_about(self, _widget):
        dialog = Gtk.AboutDialog(transient_for=self, modal=True)
        dialog.set_program_name(APP_NAME)
        dialog.set_comments(
            "A three-pane markdown notebook for the MATE / GNOME2-era desktop.")
        self._set_about_logo(dialog)
        dialog.run()
        dialog.destroy()

    def _set_about_logo(self, dialog):
        """
        Give the About dialog the same icon the app is using: the custom icon
        set when one is configured (a large PNG/SVG loaded as a pixbuf), the
        installed themed name as a fallback, else the stock icon name.
        """
        files = icon_set_files(self.settings.icon_set_dir)
        if files:
            from gi.repository import GdkPixbuf
            # Prefer the SVG, then the largest PNG, rendered at 64px.
            source = files.get("scalable")
            if source is None:
                for size in sorted((k for k in files if isinstance(k, int)),
                                   reverse=True):
                    source = files[size]
                    break
            if source is not None:
                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
                        source, 64, 64)
                    dialog.set_logo(pixbuf)
                    return
                except GLib.Error:
                    pass
            # Pixbuf load failed but a set exists: use the themed name we install.
            dialog.set_logo_icon_name(APP_ICON_NAME)
            return
        dialog.set_logo_icon_name("accessories-text-editor")

    def on_sort_changed(self, widget, mode):
        if widget.get_active():
            self.sort_mode = mode
            # Persist the choice when "remember sort order" is enabled.
            if self.settings.remember_sort:
                self.settings.set_sort_mode(mode)
                self.settings.save()
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
        self._save_session()
        Gtk.main_quit()

    def _on_delete_event(self, _widget, _event):
        if self._confirm_close_all() is False:
            return True  # cancel close
        self._save_session()
        return False

    def _save_session(self):
        """
        Persist the current workspace, the set of open notes, and the sidebar /
        note-list selection so they can be restored next launch (only meaningful
        when "restore session" is on, but we record it regardless so toggling the
        option later just works).
        """
        open_notes = [tab.note.path for tab in self._tabs
                      if tab.note is not None]
        # Current pane-2 selection (path), if any.
        sel = self.note_view.get_selection()
        _m, it = sel.get_selected()
        selected_note = self.note_store[it][1] if it is not None else None
        self.settings.set_last_session(
            self.root_folder, open_notes,
            node=self.current_node,
            subfolder=self.current_subfolder,
            selected_note=selected_note)
        self.settings.save()

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

    def _confirm(self, primary, secondary=None):
        """Yes/No confirmation dialog. Returns True if the user confirmed."""
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text=primary,
        )
        if secondary:
            dialog.format_secondary_text(secondary)
        resp = dialog.run()
        dialog.destroy()
        return resp == Gtk.ResponseType.OK
