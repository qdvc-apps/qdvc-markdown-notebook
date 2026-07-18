"""
gtk3_toolbar.py — GTK3 toolbar construction + styling for NotebookWindow.

A **mixin** combined into NotebookWindow in gtk3_window.py. GTK3-specific; relies
on handlers/attributes defined across the window and its other mixins.

User-facing labels/tooltips come from qdvc.strings (Toolbar namespace).
"""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from ..settings import TOOLBAR_TEXT_BESIDE
from ..strings import Toolbar as S


class ToolbarMixin:
    """Toolbar construction + style for NotebookWindow (see module docstring)."""

    def _build_toolbar(self):
        # Build the toolbar and return it for packing.
        #
        # GTK notes for non-GTK readers:
        #  * A Gtk.Toolbar lays out a row of Gtk.ToolButtons; insert(button, -1)
        #    appends at the end (-1 means "last position").
        #  * A plain ToolButton fires "clicked"; a Gtk.ToggleToolButton stays
        #    pressed-in and fires "toggled", with get_active() giving its state.
        #  * icon_name uses a named theme icon; set_label/set_tooltip_text add the
        #    caption and hover text.
        #  * set_sensitive(False) greys a button out (disabled); we re-enable it
        #    elsewhere when the relevant action becomes available.
        #  * set_is_important(True) marks a button so its label stays visible
        #    beside the icon in the BOTH_HORIZ toolbar style (see
        #    _toolbar_style_enum); unimportant ones become icon-only there.
        #  * connect(...) returns a handler id; we keep the read-only one
        #    (_readonly_handler) so a future caller could block it during
        #    programmatic toggles.
        toolbar = Gtk.Toolbar()
        self.toolbar = toolbar
        toolbar.set_style(self._toolbar_style_enum())

        # New tab — first item, even before New note (it opens an empty tab).
        btn_new_tab = Gtk.ToolButton(icon_name="tab-new")
        btn_new_tab.set_label(S.NEW_TAB)
        btn_new_tab.set_tooltip_text(S.NEW_TAB_TIP)
        btn_new_tab.connect("clicked", self.on_new_tab)
        toolbar.insert(btn_new_tab, -1)

        btn_new = Gtk.ToolButton(icon_name="document-new")
        btn_new.set_label(S.NEW_NOTE)
        btn_new.set_tooltip_text(S.NEW_NOTE_TIP)
        btn_new.connect("clicked", self.on_new_note)
        toolbar.insert(btn_new, -1)

        self.btn_save = Gtk.ToolButton(icon_name="document-save")
        self.btn_save.set_label(S.SAVE_NOTE)
        self.btn_save.set_tooltip_text(S.SAVE_NOTE_TIP)
        self.btn_save.set_sensitive(False)  # enabled only when dirty
        self.btn_save.connect("clicked", self.on_save_note)
        toolbar.insert(self.btn_save, -1)

        # Refresh note: reload the current note from disk (e.g. edited elsewhere).
        self.btn_refresh = Gtk.ToolButton(icon_name="view-refresh")
        self.btn_refresh.set_label(S.REFRESH_NOTE)
        self.btn_refresh.set_tooltip_text(S.REFRESH_NOTE_TIP)
        self.btn_refresh.set_sensitive(False)  # enabled only with a note open
        self.btn_refresh.connect("clicked", self.on_refresh_note)
        toolbar.insert(self.btn_refresh, -1)

        # Slugify: rename the active note from its level-1 heading. Enabled only
        # when the active tab's first line is a short (<32 char) H1.
        self.btn_slugify = Gtk.ToolButton(icon_name="insert-link")
        self.btn_slugify.set_label(S.SLUGIFY)
        self.btn_slugify.set_tooltip_text(S.SLUGIFY_TIP)
        self.btn_slugify.set_sensitive(False)
        self.btn_slugify.connect("clicked", self.on_slugify)
        toolbar.insert(self.btn_slugify, -1)

        toolbar.insert(self._toolbar_separator(), -1)

        # Card view toggle: when active, pane 2 shows each note as a small card
        # (bold title + date + first body line). Off by default.
        self.btn_cardview = Gtk.ToggleToolButton()
        self.btn_cardview.set_icon_name("mail-attachment")
        self.btn_cardview.set_label(S.CARD_VIEW)
        self.btn_cardview.set_tooltip_text(S.CARD_VIEW_TIP)
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
        self.btn_readonly.set_label(S.READ_ONLY)
        self.btn_readonly.set_tooltip_text(S.READ_ONLY_TIP)
        self.btn_readonly.set_active(True)  # default: read-only
        self.btn_readonly.set_is_important(True)
        self._readonly_handler = self.btn_readonly.connect(
            "toggled", self.on_toggle_read_only)
        toolbar.insert(self.btn_readonly, -1)

        # Preview toggle: when active, all tabs show rendered markdown (read-only)
        # and the Read-only button is disabled. Applies across all tabs.
        self.btn_preview = Gtk.ToggleToolButton()
        self.btn_preview.set_icon_name("document-page-setup")
        self.btn_preview.set_label(S.PREVIEW)
        self.btn_preview.set_tooltip_text(S.PREVIEW_TIP)
        self.btn_preview.set_active(False)
        self.btn_preview.set_is_important(True)
        self.btn_preview.connect("toggled", self.on_toggle_preview)
        toolbar.insert(self.btn_preview, -1)

        # Outline toggle: show/hide the headings-outline pane (pane 4).
        self.btn_outline = Gtk.ToggleToolButton()
        self.btn_outline.set_icon_name("view-list")
        self.btn_outline.set_label(S.OUTLINE)
        self.btn_outline.set_tooltip_text(S.OUTLINE_TIP)
        self.btn_outline.set_active(False)
        self.btn_outline.set_is_important(True)
        self.btn_outline.connect("toggled", self.on_toggle_outline)
        toolbar.insert(self.btn_outline, -1)

        toolbar.insert(self._toolbar_separator(), -1)

        # Set a custom window title.
        self.btn_set_title = Gtk.ToolButton(icon_name="document-properties")
        self.btn_set_title.set_label(S.SET_TITLE)
        self.btn_set_title.set_tooltip_text(S.SET_TITLE_TIP)
        self.btn_set_title.connect("clicked", self.on_set_window_title)
        toolbar.insert(self.btn_set_title, -1)

        return toolbar

    @staticmethod
    def _toolbar_separator():
        # A SeparatorToolItem is the vertical divider between toolbar groups.
        # set_draw(True) forces the line to actually render (otherwise it can be
        # an invisible spacer).
        sep = Gtk.SeparatorToolItem()
        sep.set_draw(True)
        return sep

    def _toolbar_style_enum(self):
        # Map our stored preference ("below"/"beside") to GTK's toolbar style
        # enum: BOTH = icon with label underneath; BOTH_HORIZ = label beside the
        # icon (but only for items flagged set_is_important).
        if self.settings.toolbar_style == TOOLBAR_TEXT_BESIDE:
            return Gtk.ToolbarStyle.BOTH_HORIZ
        return Gtk.ToolbarStyle.BOTH

    def _apply_toolbar_style(self):
        # Re-apply the style after the user changes it in Preferences. set_style
        # updates the live toolbar in place.
        self.toolbar.set_style(self._toolbar_style_enum())
