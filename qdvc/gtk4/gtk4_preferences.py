"""
gtk4_preferences.py — the Adw.PreferencesWindow for the GTK 4 front-end.

Per the common spec §9 this is an ``Adw.PreferencesWindow`` with **live-apply**
(no Save/Cancel — every change mutates the shared ``Settings`` and re-applies to
the live UI immediately, then persists). The **toolbar-style** control is
omitted (there is no toolbar in the GTK 4 UI); the **backend selector** is
present as an ``Adw.ComboRow`` with a "takes effect after restart" subtitle.

It is the GTK 4 *view* for the same ``qdvc.settings`` model the GTK 3
PreferencesDialog edits — the model is unchanged; only the widgets differ.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio  # noqa: E402

from ..settings import (
    MIN_LINE_SPACING, MAX_LINE_SPACING,
    MIN_TAB_TITLE_LENGTH, MAX_TAB_TITLE_LENGTH,
    UI_BACKEND_GTK3, UI_BACKEND_GTK4,
)
from ..strings import Prefs as P


class PreferencesWindow(Adw.PreferencesWindow):
    """Live-applying Adwaita preferences window."""

    def __init__(self, parent, settings, on_apply):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_title(P.TITLE)
        self.settings = settings
        self._on_apply = on_apply

        page = Adw.PreferencesPage()
        self.add(page)

        # ---- Fonts ----
        fonts = Adw.PreferencesGroup(title=P.GROUP_FONTS)
        page.add(fonts)
        self._editor_font_row = self._font_row(
            P.EDITOR_FONT, settings.editor_font, self._on_editor_font)
        fonts.add(self._editor_font_row)
        self._code_font_row = self._font_row(
            P.CODE_FONT, settings.code_font, self._on_code_font)
        fonts.add(self._code_font_row)
        self._preview_font_row = self._font_row(
            P.PREVIEW_FONT, settings.preview_font, self._on_preview_font)
        fonts.add(self._preview_font_row)

        # ---- Spacing ----
        spacing = Adw.PreferencesGroup(title=P.GROUP_SPACING)
        page.add(spacing)
        self._editor_spacing_row = self._spin_row(
            P.EDITOR_LINE_SPACING, settings.editor_line_spacing,
            MIN_LINE_SPACING, MAX_LINE_SPACING, self._on_editor_spacing)
        spacing.add(self._editor_spacing_row)
        self._preview_spacing_row = self._spin_row(
            P.PREVIEW_LINE_SPACING, settings.preview_line_spacing,
            MIN_LINE_SPACING, MAX_LINE_SPACING, self._on_preview_spacing)
        spacing.add(self._preview_spacing_row)

        # ---- Interface ----
        interface = Adw.PreferencesGroup(title=P.GROUP_INTERFACE)
        page.add(interface)
        self._tab_len_row = self._spin_row(
            P.TAB_TITLE_LENGTH, settings.tab_title_length,
            MIN_TAB_TITLE_LENGTH, MAX_TAB_TITLE_LENGTH, self._on_tab_len)
        interface.add(self._tab_len_row)

        # Backend selector (spec §9): Adw.ComboRow, restart subtitle.
        self._backend_row = Adw.ComboRow(title=P.UI_BACKEND_LABEL,
                                         subtitle=P.UI_BACKEND_SUBTITLE)
        backend_model = Gtk.StringList.new(
            [P.UI_BACKEND_GTK3, P.UI_BACKEND_GTK4])
        self._backend_row.set_model(backend_model)
        self._backend_row.set_selected(
            1 if settings.ui_backend == UI_BACKEND_GTK4 else 0)
        self._backend_row.connect("notify::selected", self._on_backend)
        interface.add(self._backend_row)

        # ---- Session ----
        session = Adw.PreferencesGroup(title=P.GROUP_SESSION)
        page.add(session)
        self._remember_sort_row = self._switch_row(
            P.REMEMBER_SORT, settings.remember_sort, self._on_remember_sort)
        session.add(self._remember_sort_row)
        self._restore_row = self._switch_row(
            P.RESTORE_SESSION, settings.restore_session, self._on_restore)
        session.add(self._restore_row)

    # ------------------------------------------------- row builders -- #
    def _font_row(self, title, value, on_change):
        row = Adw.ActionRow(title=title)
        btn = Gtk.FontButton()
        btn.set_font(value)
        btn.set_valign(Gtk.Align.CENTER)
        btn.connect("font-set", on_change)
        row.add_suffix(btn)
        row.set_activatable_widget(btn)
        return row

    def _spin_row(self, title, value, lo, hi, on_change):
        row = Adw.SpinRow.new_with_range(lo, hi, 1)
        row.set_title(title)
        row.set_value(value)
        row.connect("notify::value", on_change)
        return row

    def _switch_row(self, title, value, on_change):
        row = Adw.SwitchRow(title=title)
        row.set_active(bool(value))
        row.connect("notify::active", on_change)
        return row

    # ---------------------------------------------------- handlers -- #
    def _apply(self):
        if self._on_apply is not None:
            self._on_apply()
        self.settings.save()

    def _on_editor_font(self, btn):
        self.settings.set_editor_font(btn.get_font())
        self._apply()

    def _on_code_font(self, btn):
        self.settings.set_code_font(btn.get_font())
        self._apply()

    def _on_preview_font(self, btn):
        self.settings.set_preview_font(btn.get_font())
        self._apply()

    def _on_editor_spacing(self, row, _param):
        self.settings.set_editor_line_spacing(int(row.get_value()))
        self._apply()

    def _on_preview_spacing(self, row, _param):
        self.settings.set_preview_line_spacing(int(row.get_value()))
        self._apply()

    def _on_tab_len(self, row, _param):
        self.settings.set_tab_title_length(int(row.get_value()))
        self._apply()

    def _on_remember_sort(self, row, _param):
        self.settings.set_remember_sort(row.get_active())
        self._apply()

    def _on_restore(self, row, _param):
        self.settings.set_restore_session(row.get_active())
        self._apply()

    def _on_backend(self, row, _param):
        backend = (UI_BACKEND_GTK4 if row.get_selected() == 1
                   else UI_BACKEND_GTK3)
        self.settings.set_ui_backend(backend)
        # Backend change only takes effect next launch; persist, no re-apply.
        self.settings.save()
