"""
gtk4_window.py — the GTK 4 / libadwaita main window (spec §9).

The GTK 4 analogue of qdvc/gtk3/gtk3_window.NotebookWindow. It follows the GNOME
HIG and reuses the pure core (``model``, ``settings``, ``pango_markdown``,
``ui_prefs``, ``platform_utils``) unchanged — only the view mechanics differ.
The element-by-element GTK3↔GTK4 map is in docs/MAINTENANCE_GTK3_GTK4.md.

Key substitutions vs. the GTK 3 window:
  * No menubar/toolbar. A single ``Adw.HeaderBar`` carries the most-common
    actions as buttons plus a **primary menu** (``open-menu-symbolic``) whose
    ``Gio.Menu`` ends with Preferences / Keyboard Shortcuts / About.
  * Commands are ``win.*`` ``Gio.SimpleAction``s (gtk4_actions), referenced by
    name from the menu and buttons, so one action drives every surface.
  * The note list is a ``Gtk.ListView`` over a ``Gio.ListStore`` of row
    GObjects with a ``Gtk.SignalListItemFactory`` (spec §9), inside a
    ``Gtk.FilterListModel`` for search.
  * Editor tabs use ``Adw.TabView`` + ``Adw.TabBar`` (the HIG document-tabs
    widget) rather than a ``Gtk.Notebook``.
  * All modal flows are asynchronous (``Gtk.FileDialog`` / ``Adw.MessageDialog``
    + callbacks); nothing uses ``dialog.run()``.
"""

import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, GObject, GLib, Pango  # noqa: E402

from .. import model
from .. import platform_utils
from ..config import (
    APP_NAME, SORT_ALPHA, SORT_DATE_NEW, SORT_DATE_OLD,
    NODE_ALL_NOTES, NODE_INBOX, NODE_EMPTY_NOTES, NODE_SUBFOLDER,
)
from ..settings import Settings
from ..strings import Sidebar as SB, Status, Menu, Dialog as D
from .. import strings
from .gtk4_actions import ActionsMixin
from .gtk4_editorview import EditorView
from .gtk4_preferences import PreferencesWindow
from .gtk4_shortcuts import build_shortcuts_window


class NoteItem(GObject.Object):
    """Row GObject for the note-list Gio.ListStore (spec §9)."""
    __gtype_name__ = "QdvcNoteItem"

    def __init__(self, note):
        super().__init__()
        self.note = note
        self.path = note.path

    @property
    def display_name(self):
        return self.note.display_name()


class SidebarRow(GObject.Object):
    """Row GObject for the sidebar Gio.ListStore."""
    __gtype_name__ = "QdvcSidebarRow"

    def __init__(self, icon, label, node, subfolder=None):
        super().__init__()
        self.icon = icon
        self.label = label
        self.node = node
        self.subfolder = subfolder


class NotebookWindow(ActionsMixin, Adw.ApplicationWindow):
    """The GTK 4 main window (see module docstring)."""

    def __init__(self, root_folder=None, application=None):
        super().__init__(application=application)
        self.set_title(APP_NAME)
        self.set_default_size(1000, 640)

        self.settings = Settings.load()
        self.root_folder = None
        self.current_node = NODE_ALL_NOTES
        self.current_subfolder = None
        self.sort_mode = SORT_ALPHA
        if self.settings.remember_sort and self.settings.sort_mode in (
                SORT_ALPHA, SORT_DATE_NEW, SORT_DATE_OLD):
            self.sort_mode = self.settings.sort_mode
        self.read_only = True
        self.preview_mode = False
        self.card_view = False
        self.outline_visible = False
        self.search_query = None
        self._views = []          # parallel to Adw.TabView pages
        self._note_select_guard = False

        self._install_css()
        self._install_actions()
        self._build_ui()
        self._apply_fonts_to_all()

        # Start with one empty tab.
        self._new_tab(focus=False)

        if root_folder:
            self.open_folder(os.path.abspath(root_folder))
        elif self.settings.restore_session and self.settings.last_workspace:
            self._restore_last_session()

        self._update_actions_sensitivity()
        self._update_status()

    # ------------------------------------------------------------- CSS -- #
    def _install_css(self):
        """GTK 4 removed override_font; fonts are applied via a CSS provider."""
        self._css = Gtk.CssProvider()
        display = self.get_display()
        Gtk.StyleContext.add_provider_for_display(
            display, self._css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self._refresh_css()

    def _css_font_rule(self, css_class, font_desc):
        """Translate a Pango font-desc string into a CSS font rule block."""
        try:
            desc = Pango.FontDescription.from_string(font_desc)
            family = desc.get_family() or "monospace"
            size_pt = desc.get_size() / Pango.SCALE
            if size_pt <= 0:
                size_pt = 11
        except Exception:
            family, size_pt = "monospace", 11
        return (f"textview.{css_class}, textview.{css_class} text {{ "
                f"font-family: \"{family}\"; font-size: {size_pt:.0f}pt; }}")

    def _refresh_css(self):
        css = "\n".join([
            self._css_font_rule("qdvc-editor", self.settings.editor_font),
            self._css_font_rule("qdvc-preview", self.settings.preview_font),
        ])
        self._css.load_from_data(css.encode("utf-8"))

    def _apply_fonts_to_all(self):
        self._refresh_css()
        for view in self._views:
            view.apply_code_font(self.settings.code_font)

    # ------------------------------------------------------------- UI -- #
    def _build_ui(self):
        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(self._build_headerbar())
        toolbar_view.set_content(self._build_content())
        toolbar_view.add_bottom_bar(self._build_statusbar())
        self.set_content(toolbar_view)

    def _build_headerbar(self):
        header = Adw.HeaderBar()

        # Most-common actions promoted to header buttons (spec §9).
        new_note_btn = Gtk.Button.new_from_icon_name("document-new-symbolic")
        new_note_btn.set_tooltip_text(Menu.NEW_NOTE)
        new_note_btn.set_action_name("win.new-note")
        header.pack_start(new_note_btn)

        save_btn = Gtk.Button.new_from_icon_name("document-save-symbolic")
        save_btn.set_tooltip_text(Menu.SAVE_NOTE)
        save_btn.set_action_name("win.save-note")
        header.pack_start(save_btn)

        open_btn = Gtk.Button.new_from_icon_name("folder-open-symbolic")
        open_btn.set_tooltip_text(Menu.OPEN_WORKSPACE)
        open_btn.set_action_name("win.open-workspace")
        header.pack_start(open_btn)

        # Primary menu (open-menu-symbolic, set_primary) with the HIG-mandated
        # final Preferences / Keyboard Shortcuts / About section.
        menu_btn = Gtk.MenuButton()
        menu_btn.set_icon_name("open-menu-symbolic")
        menu_btn.set_primary(True)
        menu_btn.set_menu_model(self._build_primary_menu())
        header.pack_end(menu_btn)

        # View toggles promoted to the header (read-only / preview / outline).
        preview_btn = Gtk.ToggleButton()
        preview_btn.set_icon_name("view-paged-symbolic")
        preview_btn.set_tooltip_text(Menu.PREVIEW)
        preview_btn.set_action_name("win.toggle-preview")
        header.pack_end(preview_btn)

        readonly_btn = Gtk.ToggleButton()
        readonly_btn.set_icon_name("changes-prevent-symbolic")
        readonly_btn.set_tooltip_text(Menu.READ_ONLY)
        readonly_btn.set_action_name("win.toggle-read-only")
        header.pack_end(readonly_btn)

        return header

    def _build_primary_menu(self):
        menu = Gio.Menu()

        file_section = Gio.Menu()
        file_section.append(Menu.NEW_NOTE, "win.new-note")
        file_section.append(Menu.REFRESH_NOTE, "win.refresh-note")
        file_section.append(Menu.OPEN_WORKSPACE, "win.open-workspace")
        file_section.append(Menu.REFRESH_WORKSPACE, "win.refresh-workspace")
        file_section.append(Menu.CLOSE_WORKSPACE, "win.close-workspace")
        menu.append_section(None, file_section)

        tab_section = Gio.Menu()
        tab_section.append(Menu.NEW_TAB, "win.new-tab")
        tab_section.append(Menu.CLOSE_TAB, "win.close-tab")
        menu.append_section(None, tab_section)

        view_section = Gio.Menu()
        view_section.append(Menu.READ_ONLY, "win.toggle-read-only")
        view_section.append(Menu.CARD_VIEW, "win.toggle-card-view")
        view_section.append(Menu.PREVIEW, "win.toggle-preview")
        view_section.append(Menu.OUTLINE, "win.toggle-outline")
        menu.append_section(None, view_section)

        # HIG-mandated final section.
        end_section = Gio.Menu()
        end_section.append(P_PREFERENCES, "win.preferences")
        end_section.append("Keyboard Shortcuts", "win.show-help-overlay")
        end_section.append("About", "win.about")
        menu.append_section(None, end_section)
        return menu

    def _build_content(self):
        # Sidebar | note list | (tabs | outline).
        outer = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        outer.set_shrink_start_child(False)
        outer.set_shrink_end_child(False)
        outer.set_start_child(self._build_sidebar())

        inner = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        inner.set_shrink_start_child(False)
        inner.set_start_child(self._build_notelist())

        editor_split = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        editor_split.set_start_child(self._build_editor())
        editor_split.set_end_child(self._build_outline())
        editor_split.set_shrink_end_child(False)
        self._editor_split = editor_split
        self._outline_scroll.set_visible(False)

        inner.set_end_child(editor_split)
        outer.set_end_child(inner)
        outer.set_position(200)
        inner.set_position(280)
        editor_split.set_position(520)
        return outer

    # ---- sidebar (pane 1) ----
    def _build_sidebar(self):
        self.sidebar_store = Gio.ListStore(item_type=SidebarRow)
        selection = Gtk.SingleSelection(model=self.sidebar_store)
        selection.connect("selection-changed", self._on_sidebar_selection)
        self._sidebar_selection = selection

        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._sidebar_setup)
        factory.connect("bind", self._sidebar_bind)

        self.sidebar_view = Gtk.ListView(model=selection, factory=factory)
        self.sidebar_view.add_css_class("navigation-sidebar")
        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self.sidebar_view)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        return scroll

    def _sidebar_setup(self, _factory, item):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_margin_start(6)
        box.set_margin_end(6)
        box.set_margin_top(3)
        box.set_margin_bottom(3)
        icon = Gtk.Image()
        label = Gtk.Label(xalign=0)
        box.append(icon)
        box.append(label)
        item.set_child(box)

    def _sidebar_bind(self, _factory, item):
        row = item.get_item()
        box = item.get_child()
        icon = box.get_first_child()
        label = icon.get_next_sibling()
        icon.set_from_icon_name(row.icon)
        label.set_text(row.label)

    # ---- note list (pane 2) ----
    def _build_notelist(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text(SB.SEARCH_PLACEHOLDER)
        self.search_entry.connect("search-changed", self._on_search_changed)
        self.search_entry.set_margin_start(6)
        self.search_entry.set_margin_end(6)
        self.search_entry.set_margin_top(6)
        self.search_entry.set_margin_bottom(6)
        box.append(self.search_entry)

        self.note_store = Gio.ListStore(item_type=NoteItem)
        self._filter = Gtk.CustomFilter.new(self._note_filter_func)
        self._filter_model = Gtk.FilterListModel(model=self.note_store,
                                                 filter=self._filter)
        selection = Gtk.SingleSelection(model=self._filter_model)
        selection.set_autoselect(False)
        selection.set_can_unselect(True)
        selection.connect("selection-changed", self._on_note_selection)
        self._note_selection = selection

        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._note_setup)
        factory.connect("bind", self._note_bind)

        self.note_view = Gtk.ListView(model=selection, factory=factory)
        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self.note_view)
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        box.append(scroll)
        return box

    def _note_setup(self, _factory, item):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_start(8)
        box.set_margin_end(8)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        title = Gtk.Label(xalign=0)
        title.add_css_class("heading")
        subtitle = Gtk.Label(xalign=0)
        subtitle.add_css_class("dim-label")
        subtitle.add_css_class("caption")
        subtitle.set_wrap(True)
        box.append(title)
        box.append(subtitle)
        item.set_child(box)

    def _note_bind(self, _factory, item):
        note_item = item.get_item()
        box = item.get_child()
        title = box.get_first_child()
        subtitle = title.get_next_sibling()
        title.set_text(note_item.display_name)
        if self.card_view:
            date = model.format_mtime(note_item.note)
            snippet = model.first_body_line(note_item.note)
            subtitle.set_text("  ".join(x for x in (date, snippet) if x))
            subtitle.set_visible(True)
        else:
            subtitle.set_visible(False)

    def _note_filter_func(self, note_item):
        if not self.search_query:
            return True
        return model.note_matches(note_item.note, self.search_query.lower())

    # ---- editor (pane 3): Adw.TabView + Adw.TabBar ----
    def _build_editor(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.tab_view = Adw.TabView()
        self.tab_view.connect("notify::selected-page", self._on_tab_switched)
        self.tab_view.connect("close-page", self._on_close_page)
        tab_bar = Adw.TabBar(view=self.tab_view)
        box.append(tab_bar)
        box.append(self.tab_view)
        self.tab_view.set_vexpand(True)
        return box

    # ---- outline (pane 4) ----
    def _build_outline(self):
        # A flat ListView of headings; indent is encoded in the label text.
        self._outline_list = Gio.ListStore(item_type=OutlineItem)
        selection = Gtk.SingleSelection(model=self._outline_list)
        selection.set_autoselect(False)
        selection.set_can_unselect(True)
        selection.connect("selection-changed", self._on_outline_selection)
        self._outline_selection = selection
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._outline_setup)
        factory.connect("bind", self._outline_bind)
        self.outline_view = Gtk.ListView(model=selection, factory=factory)
        self._outline_scroll = Gtk.ScrolledWindow()
        self._outline_scroll.set_child(self.outline_view)
        self._outline_scroll.set_policy(Gtk.PolicyType.NEVER,
                                        Gtk.PolicyType.AUTOMATIC)
        return self._outline_scroll

    def _outline_setup(self, _factory, item):
        label = Gtk.Label(xalign=0)
        label.set_margin_start(6)
        label.set_margin_end(6)
        label.set_margin_top(2)
        label.set_margin_bottom(2)
        item.set_child(label)

    def _outline_bind(self, _factory, item):
        oi = item.get_item()
        label = item.get_child()
        label.set_text("  " * (oi.level - 1) + oi.title)

    # ---- status bar ----
    def _build_statusbar(self):
        self.status_label = Gtk.Label(xalign=0)
        self.status_label.set_margin_start(8)
        self.status_label.set_margin_end(8)
        self.status_label.set_margin_top(2)
        self.status_label.set_margin_bottom(2)
        return self.status_label

    # ================================================= tab management == #
    def _active_view(self):
        page = self.tab_view.get_selected_page()
        if page is None:
            return None
        child = page.get_child()
        for v in self._views:
            if v.widget is child:
                return v
        return None

    def _new_tab(self, focus=True):
        view = EditorView(on_changed=self._on_view_changed,
                          code_font=self.settings.code_font)
        view.apply_code_font(self.settings.code_font)
        view.set_read_only(True)
        view.set_preview(False)
        self._views.append(view)
        page = self.tab_view.append(view.widget)
        page.set_title(view.title_text())
        if focus:
            self.tab_view.set_selected_page(page)
            view.text_view.grab_focus()
        self._update_status()
        return view

    def _page_for_view(self, view):
        return self.tab_view.get_page(view.widget)

    def on_new_tab(self, _action, _param):
        self._new_tab(focus=True)

    def on_close_tab(self, _action, _param):
        page = self.tab_view.get_selected_page()
        if page is not None and self.tab_view.get_n_pages() > 1:
            self.tab_view.close_page(page)

    def _on_close_page(self, tab_view, page):
        # Never close the last tab.
        if tab_view.get_n_pages() <= 1:
            tab_view.close_page_finish(page, False)
            return True
        view = None
        for v in self._views:
            if v.widget is page.get_child():
                view = v
                break

        def finish(confirm):
            if confirm and view is not None and view in self._views:
                self._views.remove(view)
            tab_view.close_page_finish(page, confirm)
            self._update_status()

        if view is not None and view.dirty and view.note:
            self._confirm_discard(view, lambda ok: finish(ok))
            return True
        finish(True)
        return True

    def on_next_tab(self, _action, _param):
        self.tab_view.select_next_page()

    def on_prev_tab(self, _action, _param):
        self.tab_view.select_previous_page()

    def on_goto_tab(self, _action, param):
        idx = param.get_int32()
        if 0 <= idx < self.tab_view.get_n_pages():
            page = self.tab_view.get_nth_page(idx)
            self.tab_view.set_selected_page(page)

    def _on_tab_switched(self, _tab_view, _param):
        view = self._active_view()
        if view is not None:
            self.read_only = view.read_only
            self.preview_mode = view.preview
            self._set_toggle_state("toggle-read-only", view.read_only)
            self._set_toggle_state("toggle-preview", view.preview)
            view.highlight_search(self.search_query)
            self._sync_panes_to_view(view)
            self._refresh_outline(view)
        self._update_status()

    def _on_view_changed(self, view):
        if view is self._active_view():
            self._refresh_outline(view)
        self._update_status()

    # ================================================= sidebar / panes = #
    def _reload_sidebar(self):
        self.sidebar_store.remove_all()
        if not self.root_folder:
            return
        self.sidebar_store.append(
            SidebarRow("emblem-documents-symbolic", SB.ALL_NOTES,
                       NODE_ALL_NOTES))
        self.sidebar_store.append(
            SidebarRow("mail-inbox-symbolic", SB.INBOX, NODE_INBOX))
        self.sidebar_store.append(
            SidebarRow("edit-clear-symbolic", SB.EMPTY_NOTES,
                       NODE_EMPTY_NOTES))
        for name in model.immediate_subfolders(self.root_folder):
            self.sidebar_store.append(
                SidebarRow("folder-symbolic", name, NODE_SUBFOLDER, name))
        # Select the current node (default All Notes).
        self._select_sidebar_node(self.current_node, self.current_subfolder)

    def _select_sidebar_node(self, node, subfolder=None):
        for i in range(self.sidebar_store.get_n_items()):
            row = self.sidebar_store.get_item(i)
            if row.node == node and (node != NODE_SUBFOLDER
                                     or row.subfolder == subfolder):
                self._sidebar_selection.set_selected(i)
                return True
        return False

    def _on_sidebar_selection(self, selection, _pos, _n):
        row = selection.get_selected_item()
        if row is None:
            return
        self.current_node = row.node
        self.current_subfolder = row.subfolder
        self._reload_notelist()

    def _notes_for_current_node(self):
        root = self.root_folder
        if not root:
            return []
        if self.current_node == NODE_INBOX:
            return model.collect_top_level_notes(root)
        if self.current_node == NODE_EMPTY_NOTES:
            return model.collect_empty_notes(root)
        if self.current_node == NODE_SUBFOLDER and self.current_subfolder:
            return model.collect_notes(
                os.path.join(root, self.current_subfolder))
        return model.collect_notes(root)

    def _reload_notelist(self, select_path=None):
        notes = model.sort_notes(self._notes_for_current_node(),
                                 self.sort_mode)
        self.note_store.remove_all()
        for note in notes:
            self.note_store.append(NoteItem(note))
        self._filter.changed(Gtk.FilterChange.DIFFERENT)
        if select_path:
            self._select_note_path(select_path)
        self._update_status()

    def _select_note_path(self, path):
        self._note_select_guard = True
        try:
            for i in range(self._filter_model.get_n_items()):
                if self._filter_model.get_item(i).path == path:
                    self._note_selection.set_selected(i)
                    break
        finally:
            self._note_select_guard = False

    def _on_note_selection(self, selection, _pos, _n):
        if self._note_select_guard:
            return
        item = selection.get_selected_item()
        if item is None:
            return
        view = self._active_view()
        if view is None:
            return
        # Confirm unsaved edits before replacing the active tab's content.
        if view.dirty and view.note:
            def after(ok):
                if ok:
                    self._load_note_in_active(item.note)
                else:
                    self._select_note_path(view.note.path)
            self._confirm_discard(view, after)
        else:
            self._load_note_in_active(item.note)

    def _load_note_in_active(self, note):
        view = self._active_view()
        if view is None:
            return
        if not view.load_note(note):
            self._error(D.err_open(note.path))
            return
        view.highlight_search(self.search_query)
        page = self._page_for_view(view)
        if page is not None:
            page.set_title(view.title_text())
        self._refresh_outline(view)
        self._update_status()
        self._update_actions_sensitivity()

    def _sync_panes_to_view(self, view):
        if view is None or view.note is None:
            return
        self._select_note_path(view.note.path)

    # ================================================= search ========= #
    def _on_search_changed(self, entry):
        text = entry.get_text().strip()
        self.search_query = text or None
        self._filter.changed(Gtk.FilterChange.DIFFERENT)
        view = self._active_view()
        if view is not None:
            view.highlight_search(self.search_query)
        self._update_status()

    # ================================================= outline ======== #
    def _refresh_outline(self, view=None):
        if not self.outline_visible:
            return
        view = view or self._active_view()
        self._outline_list.remove_all()
        if view is None:
            return
        for h in model.parse_headings(view.get_content()):
            self._outline_list.append(
                OutlineItem(h["level"], h["title"], h["line"]))

    def _on_outline_selection(self, selection, _pos, _n):
        oi = selection.get_selected_item()
        if oi is None:
            return
        view = self._active_view()
        if view is not None:
            view.scroll_to_line(oi.line)

    # ================================================= view toggles === #
    def on_toggle_read_only(self, action, value):
        self.read_only = bool(value)
        action.set_state(value)
        view = self._active_view()
        if view is not None:
            view.set_read_only(self.read_only)
        self._update_status()
        self._update_actions_sensitivity()

    def on_toggle_preview(self, action, value):
        self.preview_mode = bool(value)
        action.set_state(value)
        view = self._active_view()
        if view is not None:
            view.set_preview(self.preview_mode)
        self._set_action_enabled("toggle-read-only", not self.preview_mode)
        self._refresh_outline()
        self._update_status()

    def on_toggle_card_view(self, action, value):
        self.card_view = bool(value)
        action.set_state(value)
        keep = None
        view = self._active_view()
        if view and view.note:
            keep = view.note.path
        self._reload_notelist(select_path=keep)

    def on_toggle_outline(self, action, value):
        self.outline_visible = bool(value)
        action.set_state(value)
        self._outline_scroll.set_visible(self.outline_visible)
        if self.outline_visible:
            self._refresh_outline()

    # ================================================= file commands == #
    def on_new_note(self, _action, _param):
        if self.read_only or not self.root_folder:
            return
        folder = self.root_folder
        if self.current_node == NODE_SUBFOLDER and self.current_subfolder:
            folder = os.path.join(folder, self.current_subfolder)
        try:
            note = model.create_empty_note(folder)
        except OSError as exc:
            self._error(str(exc))
            return
        self._reload_notelist(select_path=note.path)
        self._load_note_in_active(note)

    def on_save_note(self, _action, _param):
        view = self._active_view()
        if view is None or not view.note:
            return
        if not view.save():
            self._error(D.err_save(view.note.path))
        page = self._page_for_view(view)
        if page is not None:
            page.set_title(view.title_text())
        self._update_status()
        self._update_actions_sensitivity()

    def on_refresh_note(self, _action, _param):
        view = self._active_view()
        if view is None or not view.note:
            return

        def do_reload():
            fresh = model.Note(view.note.path)
            if view.load_note(fresh):
                view.highlight_search(self.search_query)
                self._refresh_outline(view)
                self._update_status()

        if view.dirty:
            self._confirm_discard(view, lambda ok: do_reload() if ok else None)
        else:
            do_reload()

    def on_slugify(self, _action, _param):
        view = self._active_view()
        if view is None or not view.note or self.read_only:
            return
        heading = model.heading_for_slug(view.get_content())
        if not heading:
            return
        base = model.slugify(heading)
        if not base:
            return
        old_name_preview = view.note.display_name()

        def after(ok):
            if not ok:
                return
            try:
                model.rename_note(view.note, base)
            except OSError as exc:
                self._error(D.err_rename(str(exc)))
                return
            page = self._page_for_view(view)
            if page is not None:
                page.set_title(view.title_text())
            self._reload_notelist(select_path=view.note.path)
            self._update_status()

        self._confirm("Rename note",
                      D.confirm_rename_body(old_name_preview, base + ".md"),
                      after)

    # ================================================= workspace ====== #
    def on_open_workspace(self, _action, _param):
        dialog = Gtk.FileDialog()
        dialog.set_title(D.OPEN_FOLDER_TITLE)

        def on_pick(dlg, result):
            try:
                folder = dlg.select_folder_finish(result)
            except GLib.Error:
                return
            if folder is not None:
                self.open_folder(folder.get_path())

        dialog.select_folder(self, None, on_pick)

    def open_folder(self, folder):
        if not folder or not os.path.isdir(folder):
            self._error(D.not_a_folder(folder))
            return
        self.root_folder = folder
        self.current_node = NODE_ALL_NOTES
        self.current_subfolder = None
        self._update_window_title()
        self._reload_sidebar()
        self._reload_notelist()
        view = self._active_view()
        if view:
            view.clear()
            page = self._page_for_view(view)
            if page is not None:
                page.set_title(view.title_text())
        self.settings.add_recent_folder(folder)
        self.settings.save()
        self._update_status()
        self._update_actions_sensitivity()

    def on_refresh_workspace(self, _action, _param):
        if not self.root_folder:
            return
        node, sub = self.current_node, self.current_subfolder
        self._reload_sidebar()
        self._select_sidebar_node(node, sub)
        self._reload_notelist()

    def on_close_workspace(self, _action, _param):
        def finish(ok):
            if not ok:
                return
            self.root_folder = None
            self.sidebar_store.remove_all()
            self.note_store.remove_all()
            self._filter.changed(Gtk.FilterChange.DIFFERENT)
            view = self._active_view()
            if view:
                view.clear()
            self._update_window_title()
            self._update_status()
            self._update_actions_sensitivity()
        self._confirm_close_all(finish)

    def _update_window_title(self):
        if self.root_folder:
            self.set_title(f"{APP_NAME} \u2014 {self.root_folder}")
        else:
            self.set_title(APP_NAME)

    # ================================================= prefs / about == #
    def on_preferences(self, _action, _param):
        win = PreferencesWindow(self, self.settings, self._apply_preferences)
        win.present()

    def _apply_preferences(self):
        self._refresh_css()
        for view in self._views:
            view.apply_code_font(self.settings.code_font)

    def on_about(self, _action, _param):
        about = Adw.AboutWindow(transient_for=self) \
            if hasattr(Adw, "AboutWindow") else None
        if about is not None:
            about.set_application_name(APP_NAME)
            about.set_comments(strings.APP_COMMENTS)
            from .gtk4_app import ICON_NAME
            about.set_application_icon(ICON_NAME)
            about.present()
        else:  # pragma: no cover - very old libadwaita
            dlg = Gtk.AboutDialog(transient_for=self, modal=True)
            dlg.set_program_name(APP_NAME)
            dlg.set_comments(strings.APP_COMMENTS)
            dlg.present()

    # ================================================= quit / session = #
    def on_quit(self, _action, _param):
        def finish(ok):
            if not ok:
                return
            self._save_session()
            app = self.get_application()
            if app is not None:
                app.quit()
        self._confirm_close_all(finish)

    def _save_session(self):
        open_notes = [v.note.path for v in self._views if v.note is not None]
        sel = self._note_selection.get_selected_item()
        selected = sel.path if sel is not None else None
        self.settings.set_last_session(
            self.root_folder, open_notes,
            node=self.current_node, subfolder=self.current_subfolder,
            selected_note=selected)
        self.settings.save()

    def _restore_last_session(self):
        folder = self.settings.last_workspace
        if not folder or not os.path.isdir(folder):
            return
        self.open_folder(os.path.abspath(folder))
        node = self.settings.last_node
        if node in (NODE_ALL_NOTES, NODE_INBOX, NODE_EMPTY_NOTES,
                    NODE_SUBFOLDER):
            self._select_sidebar_node(node, self.settings.last_subfolder)
        notes = [p for p in self.settings.last_open_notes
                 if isinstance(p, str) and os.path.isfile(p)]
        first = True
        for path in notes:
            if first:
                self._load_note_in_active(model.Note(path))
                first = False
            else:
                v = self._new_tab(focus=False)
                v.load_note(model.Note(path))
                page = self._page_for_view(v)
                if page is not None:
                    page.set_title(v.title_text())
        sel = self.settings.last_selected_note
        if sel and os.path.isfile(sel):
            self._select_note_path(sel)

    # ================================================= status ========= #
    def _update_status(self):
        if self.preview_mode:
            mode = Status.MODE_PREVIEW
        elif self.read_only:
            mode = Status.MODE_READ_ONLY
        else:
            mode = Status.MODE_EDIT
        count = self.note_store.get_n_items()
        view = self._active_view()
        sel = view.note.display_name() if (view and view.note) \
            else Status.SELECTED_NONE
        msg = strings.status_items(count, sel)
        if view and view.dirty:
            msg += "  *"
        self.status_label.set_markup(f"<b>{mode}</b>   {GLib.markup_escape_text(msg)}")
        self._update_actions_sensitivity()

    # ================================================= dialogs ======== #
    def _error(self, message):
        dlg = Adw.MessageDialog(transient_for=self, heading="Error",
                                body=message)
        dlg.add_response("ok", "_OK")
        dlg.present()

    def _confirm(self, heading, body, callback):
        dlg = Adw.MessageDialog(transient_for=self, heading=heading, body=body)
        dlg.add_response("cancel", D.BTN_CANCEL.replace("_", ""))
        dlg.add_response("ok", "_OK")
        dlg.set_default_response("ok")
        dlg.set_close_response("cancel")

        def on_response(_dlg, response):
            callback(response == "ok")
        dlg.connect("response", on_response)
        dlg.present()

    def _confirm_discard(self, view, callback):
        name = view.note.display_name() if view.note else ""
        dlg = Adw.MessageDialog(
            transient_for=self,
            heading=D.save_changes_prompt(name),
            body="")
        dlg.add_response("cancel", D.BTN_CANCEL.replace("_", ""))
        dlg.add_response("discard", "_Discard")
        dlg.set_response_appearance("discard",
                                    Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.set_close_response("cancel")

        def on_response(_dlg, response):
            callback(response == "discard")
        dlg.connect("response", on_response)
        dlg.present()

    def _confirm_close_all(self, callback):
        dirty = [v for v in self._views if v.dirty and v.note]
        if not dirty:
            callback(True)
            return
        # Confirm the dirty tabs one at a time.
        pending = list(dirty)

        def step(ok):
            if not ok:
                callback(False)
                return
            if pending:
                v = pending.pop(0)
                self._confirm_discard(v, step)
            else:
                callback(True)
        step(True)


class OutlineItem(GObject.Object):
    """Row GObject for the outline ListView."""
    __gtype_name__ = "QdvcOutlineItem"

    def __init__(self, level, title, line):
        super().__init__()
        self.level = level
        self.title = title
        self.line = line


# Preferences label reused in the primary menu (strip the trailing ellipsis so
# the menu item reads cleanly).
P_PREFERENCES = Menu.PREFERENCES
