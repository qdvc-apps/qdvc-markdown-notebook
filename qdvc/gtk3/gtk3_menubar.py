"""
gtk3_menubar.py — GTK3 menu-bar construction for NotebookWindow.

This is a **mixin**: it holds only the menu-building methods, factored out of the
window for readability. It is combined into NotebookWindow in gtk3_window.py and
relies on attributes/handlers defined there and in the other mixins (e.g.
self.on_new_note, self.settings). No standalone behaviour; GTK3-specific.

All user-facing text comes from qdvc.strings (the Menu namespace) so it
can be translated in one place.
"""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from ..config import SORT_ALPHA, SORT_DATE_NEW, SORT_DATE_OLD
from ..strings import Menu
from .gtk3_shortcuts import add_menu_accel


class MenuBarMixin:
    """Menu-bar construction for NotebookWindow (see module docstring)."""

    def _build_menubar(self):
        # Build the whole menu bar top-down and return it for packing.
        #
        # GTK notes for non-GTK readers:
        #  * A Gtk.MenuBar holds top-level Gtk.MenuItems; each gets a submenu
        #    (a Gtk.Menu) via set_submenu(). Items inside the submenu are also
        #    Gtk.MenuItems; "activate" is the signal emitted when one is chosen.
        #  * Keyboard shortcuts work through an "accel group": you create one,
        #    register it on the window (add_accel_group), then each item calls
        #    add_accelerator(signal, group, key, modifiers, flags) to bind a key
        #    combo. Gdk.KEY_* are key codes; Gdk.ModifierType.* are Ctrl/Shift/…
        #  * new_with_mnemonic("_File") makes the letter after "_" the Alt-access
        #    key (Alt+F opens this menu).
        #  * connect("activate", handler) wires the click/keypress to a Python
        #    method; extra args after the handler are passed through to it.
        menubar = Gtk.MenuBar()
        accel = Gtk.AccelGroup()
        self.add_accel_group(accel)
        self._accel_group = accel

        # ---- File menu ----
        file_menu = Gtk.Menu()
        file_item = Gtk.MenuItem.new_with_mnemonic(Menu.FILE)
        file_item.set_submenu(file_menu)

        mi_new = self._icon_menu_item(Menu.NEW_NOTE, "document-new")
        add_menu_accel(mi_new, accel, "new-note")
        mi_new.connect("activate", self.on_new_note)
        file_menu.append(mi_new)

        mi_save = self._icon_menu_item(Menu.SAVE_NOTE, "document-save")
        add_menu_accel(mi_save, accel, "save-note")
        mi_save.connect("activate", self.on_save_note)
        file_menu.append(mi_save)

        # Refresh note — mirrors the toolbar button; Ctrl+R. Disabled until a
        # note is open (kept in sync in _update_save_sensitivity).
        self.mi_refresh = self._icon_menu_item(Menu.REFRESH_NOTE, "view-refresh")
        add_menu_accel(self.mi_refresh, accel, "refresh-note")
        self.mi_refresh.set_sensitive(False)
        self.mi_refresh.connect("activate", self.on_refresh_note)
        file_menu.append(self.mi_refresh)

        # SeparatorMenuItem draws the thin divider line between item groups.
        file_menu.append(Gtk.SeparatorMenuItem())

        mi_open = self._icon_menu_item(Menu.OPEN_WORKSPACE, "folder-open")
        add_menu_accel(mi_open, accel, "open-workspace")
        mi_open.connect("activate", self.on_open_folder)
        file_menu.append(mi_open)

        # Refresh workspace — re-scan the working folder and rebuild panes 1+2
        # from disk. Same icon as Refresh note. Ctrl+Shift+R.
        self.mi_refresh_ws = self._icon_menu_item(Menu.REFRESH_WORKSPACE,
                                                  "view-refresh")
        add_menu_accel(self.mi_refresh_ws, accel, "refresh-workspace")
        self.mi_refresh_ws.connect("activate", self.on_refresh_workspace)
        file_menu.append(self.mi_refresh_ws)

        mi_close_ws = Gtk.MenuItem(label=Menu.CLOSE_WORKSPACE)
        mi_close_ws.connect("activate", self.on_close_workspace)
        file_menu.append(mi_close_ws)

        # "Open recent workspace" submenu, populated dynamically from settings.
        # We keep references on self so _rebuild_recent_menu can refill it later.
        self.recent_menu_item = self._icon_menu_item(
            Menu.OPEN_RECENT_WORKSPACE, "document-open-recent")
        self.recent_menu = Gtk.Menu()
        self.recent_menu_item.set_submenu(self.recent_menu)
        file_menu.append(self.recent_menu_item)

        file_menu.append(Gtk.SeparatorMenuItem())

        mi_new_tab = self._icon_menu_item(Menu.NEW_TAB, "tab-new")
        add_menu_accel(mi_new_tab, accel, "new-tab")
        mi_new_tab.connect("activate", self.on_new_tab)
        file_menu.append(mi_new_tab)

        mi_close_tab = Gtk.MenuItem(label=Menu.CLOSE_TAB)
        add_menu_accel(mi_close_tab, accel, "close-tab")
        mi_close_tab.connect("activate", self.on_close_tab)
        file_menu.append(mi_close_tab)

        file_menu.append(Gtk.SeparatorMenuItem())

        mi_quit = self._icon_menu_item(Menu.QUIT, "application-exit")
        # Note: the spec listed Ctrl+S for Quit; that collides with Save,
        # so Quit is bound to the conventional Ctrl+Q instead. See MAINTENANCE.md.
        add_menu_accel(mi_quit, accel, "quit")
        mi_quit.connect("activate", self.on_quit)
        file_menu.append(mi_quit)

        menubar.append(file_item)

        # ---- Edit menu ----
        edit_menu = Gtk.Menu()
        edit_item = Gtk.MenuItem.new_with_mnemonic(Menu.EDIT)
        edit_item.set_submenu(edit_menu)

        mi_prefs = self._icon_menu_item(Menu.PREFERENCES, "preferences-system")
        add_menu_accel(mi_prefs, accel, "preferences")
        mi_prefs.connect("activate", self.on_preferences)
        edit_menu.append(mi_prefs)

        mi_set_title = self._icon_menu_item(Menu.SET_WINDOW_TITLE,
                                            "document-properties")
        mi_set_title.connect("activate", self.on_set_window_title)
        edit_menu.append(mi_set_title)

        menubar.append(edit_item)

        # ---- View menu ----
        view_menu = Gtk.Menu()
        view_item = Gtk.MenuItem.new_with_mnemonic(Menu.VIEW)
        view_item.set_submenu(view_menu)

        # CheckMenuItem shows a tick box; its "toggled" signal fires on change
        # and its get_active() reports the checked state.
        self.mi_toolbar = Gtk.CheckMenuItem(label=Menu.TOOLBAR)
        self.mi_toolbar.set_active(True)
        self.mi_toolbar.connect("toggled", self.on_toggle_toolbar)
        view_menu.append(self.mi_toolbar)

        self.mi_statusbar = Gtk.CheckMenuItem(label=Menu.STATUSBAR)
        self.mi_statusbar.set_active(True)
        self.mi_statusbar.connect("toggled", self.on_toggle_statusbar)
        view_menu.append(self.mi_statusbar)

        view_menu.append(Gtk.SeparatorMenuItem())

        # Mode toggles that mirror the toolbar's toggle buttons. A guard flag
        # (_syncing_view_toggles) prevents the menu↔toolbar sync from looping.
        self._syncing_view_toggles = False

        self.mi_readonly = Gtk.CheckMenuItem(label=Menu.READ_ONLY)
        self.mi_readonly.set_active(True)
        add_menu_accel(self.mi_readonly, accel, "toggle-read-only")
        self.mi_readonly.connect("toggled", self.on_menu_toggle_read_only)
        view_menu.append(self.mi_readonly)

        self.mi_cardview = Gtk.CheckMenuItem(label=Menu.CARD_VIEW)
        add_menu_accel(self.mi_cardview, accel, "toggle-card-view")
        self.mi_cardview.connect("toggled", self.on_menu_toggle_card_view)
        view_menu.append(self.mi_cardview)

        self.mi_preview = Gtk.CheckMenuItem(label=Menu.PREVIEW)
        add_menu_accel(self.mi_preview, accel, "toggle-preview")
        self.mi_preview.connect("toggled", self.on_menu_toggle_preview)
        view_menu.append(self.mi_preview)

        self.mi_outline = Gtk.CheckMenuItem(label=Menu.OUTLINE)
        add_menu_accel(self.mi_outline, accel, "toggle-outline")
        self.mi_outline.connect("toggled", self.on_menu_toggle_outline)
        view_menu.append(self.mi_outline)

        view_menu.append(Gtk.SeparatorMenuItem())

        # RadioMenuItems share a group so exactly one is active. The first uses
        # group=None to start a new group; the rest pass the first as their
        # group. The extra SORT_* arg is handed to on_sort_changed on toggle.
        mi_alpha = Gtk.RadioMenuItem(label=Menu.SORT_ALPHA, group=None)
        mi_alpha.set_active(True)
        mi_alpha.connect("toggled", self.on_sort_changed, SORT_ALPHA)
        view_menu.append(mi_alpha)

        mi_new_first = Gtk.RadioMenuItem(label=Menu.SORT_DATE_NEW,
                                         group=mi_alpha)
        mi_new_first.connect("toggled", self.on_sort_changed, SORT_DATE_NEW)
        view_menu.append(mi_new_first)

        mi_old_first = Gtk.RadioMenuItem(label=Menu.SORT_DATE_OLD,
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
        help_item = Gtk.MenuItem.new_with_mnemonic(Menu.HELP)
        help_item.set_submenu(help_menu)

        mi_about = self._icon_menu_item(Menu.ABOUT, "help-about")
        mi_about.connect("activate", self.on_about)
        help_menu.append(mi_about)

        menubar.append(help_item)
        return menubar

    # Per-name fallbacks for themed icons that some minimal themes omit, so a
    # missing icon never leaves a broken/blank slot (spec §8). Each maps a
    # possibly-absent name to a near-universal stock name.
    _ICON_FALLBACKS = {
        "help-about": "dialog-information",
        "document-open-recent": "document-open",
        "document-properties": "preferences-system",
        "tab-new": "document-new",
    }

    @classmethod
    def _resolve_icon_name(cls, icon_name):
        """
        Return icon_name if the current icon theme has it, else a sensible
        fallback (or the original name if none is registered). Best-effort: if
        the theme can't be queried, the original name is returned unchanged.
        """
        try:
            theme = Gtk.IconTheme.get_default()
            if theme.has_icon(icon_name):
                return icon_name
            fallback = cls._ICON_FALLBACKS.get(icon_name)
            if fallback and theme.has_icon(fallback):
                return fallback
        except Exception:
            pass
        return icon_name

    @classmethod
    def _icon_menu_item(cls, label, icon_name):
        """
        Build a menu item with a leading icon, GNOME2/MATE style.

        Uses Gtk.ImageMenuItem (deprecated in GTK3 but the idiomatic way to get
        icons in menus, and a good fit for this app's MATE-era look). It pairs a
        label with a Gtk.Image built from a named theme icon at MENU size;
        set_always_show_image forces the icon to show even on themes that hide
        menu icons by default. The icon name is resolved against the current
        theme with a graceful fallback (see _resolve_icon_name) so a missing
        themed icon never leaves a broken slot. Falls back to a plain MenuItem
        (no icon) if ImageMenuItem is unavailable on the running GTK build.
        """
        try:
            item = Gtk.ImageMenuItem(label=label)
            resolved = cls._resolve_icon_name(icon_name)
            img = Gtk.Image.new_from_icon_name(resolved, Gtk.IconSize.MENU)
            item.set_image(img)
            item.set_always_show_image(True)
            return item
        except (AttributeError, TypeError):
            return Gtk.MenuItem(label=label)
