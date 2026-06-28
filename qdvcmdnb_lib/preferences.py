"""
preferences.py — the Preferences dialog for QDVC Markdown Notebook.

In the GNOME2 / MATE idiom this is "Preferences" (under the Edit menu). It is a
tabbed dialog:

  * Fonts     — editor font, code font, markdown-preview font, and the editor /
                preview line spacing.
  * Interface — toolbar button text placement (beside vs below the icon).

Behaviour: changes preview live in the app while the dialog is open. The dialog
has Save and Cancel buttons — Save persists the settings to disk; Cancel (or
closing the window) restores the values that were in effect when the dialog
opened and re-applies them, discarding the live preview.
"""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from .settings import (
    TOOLBAR_TEXT_BESIDE,
    TOOLBAR_TEXT_BELOW,
    MIN_LINE_SPACING,
    MAX_LINE_SPACING,
)


class PreferencesDialog(Gtk.Dialog):

    def __init__(self, parent, settings, on_apply):
        super().__init__(title="Preferences", transient_for=parent, modal=True)
        self.settings = settings
        self._on_apply = on_apply

        # Snapshot the values in effect when the dialog opened, so Cancel can
        # restore them (and revert the live preview).
        self._original = {
            "editor_font": settings.editor_font,
            "code_font": settings.code_font,
            "preview_font": settings.preview_font,
            "editor_line_spacing": settings.editor_line_spacing,
            "preview_line_spacing": settings.preview_line_spacing,
            "toolbar_style": settings.toolbar_style,
        }

        self.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        self.add_button("_Save", Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)
        self.set_default_size(460, -1)

        notebook = Gtk.Notebook()
        notebook.set_border_width(8)
        notebook.append_page(self._build_fonts_tab(), Gtk.Label(label="Fonts"))
        notebook.append_page(self._build_interface_tab(),
                             Gtk.Label(label="Interface"))

        content = self.get_content_area()
        content.set_spacing(12)
        content.set_border_width(8)
        content.add(notebook)

        self.show_all()

    # -------------------------------------------------------- Fonts tab -- #
    def _build_fonts_tab(self):
        grid = Gtk.Grid(row_spacing=8, column_spacing=12)
        grid.set_border_width(12)

        row = 0
        grid.attach(self._label("Editor font:"), 0, row, 1, 1)
        self.editor_font_btn = Gtk.FontButton()
        self.editor_font_btn.set_font(self.settings.editor_font)
        self.editor_font_btn.set_hexpand(True)
        self.editor_font_btn.connect("font-set", self._on_editor_font_set)
        grid.attach(self.editor_font_btn, 1, row, 1, 1)

        row += 1
        grid.attach(self._label("Code font:"), 0, row, 1, 1)
        self.code_font_btn = Gtk.FontButton()
        self.code_font_btn.set_font(self.settings.code_font)
        self.code_font_btn.set_hexpand(True)
        self.code_font_btn.connect("font-set", self._on_code_font_set)
        grid.attach(self.code_font_btn, 1, row, 1, 1)

        row += 1
        grid.attach(self._label("Markdown preview font:"), 0, row, 1, 1)
        self.preview_font_btn = Gtk.FontButton()
        self.preview_font_btn.set_font(self.settings.preview_font)
        self.preview_font_btn.set_hexpand(True)
        self.preview_font_btn.connect("font-set", self._on_preview_font_set)
        grid.attach(self.preview_font_btn, 1, row, 1, 1)

        row += 1
        grid.attach(self._label("Editor line spacing:"), 0, row, 1, 1)
        self.editor_spacing_spin = self._spacing_spin(
            self.settings.editor_line_spacing, self._on_editor_spacing_changed)
        grid.attach(self.editor_spacing_spin, 1, row, 1, 1)

        row += 1
        grid.attach(self._label("Preview line spacing:"), 0, row, 1, 1)
        self.preview_spacing_spin = self._spacing_spin(
            self.settings.preview_line_spacing,
            self._on_preview_spacing_changed)
        grid.attach(self.preview_spacing_spin, 1, row, 1, 1)

        return grid

    def _spacing_spin(self, value, handler):
        spin = Gtk.SpinButton.new_with_range(
            MIN_LINE_SPACING, MAX_LINE_SPACING, 1)
        spin.set_value(value)
        spin.set_halign(Gtk.Align.START)
        spin.connect("value-changed", handler)
        return spin

    def _on_editor_font_set(self, btn):
        # Live preview only — not persisted until Save.
        self.settings.set_editor_font(btn.get_font())
        self._on_apply()

    def _on_code_font_set(self, btn):
        self.settings.set_code_font(btn.get_font())
        self._on_apply()

    def _on_preview_font_set(self, btn):
        self.settings.set_preview_font(btn.get_font())
        self._on_apply()

    def _on_editor_spacing_changed(self, spin):
        self.settings.set_editor_line_spacing(spin.get_value_as_int())
        self._on_apply()

    def _on_preview_spacing_changed(self, spin):
        self.settings.set_preview_line_spacing(spin.get_value_as_int())
        self._on_apply()

    # ---------------------------------------------------- Interface tab -- #
    def _build_interface_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_border_width(12)

        label = Gtk.Label(label="Toolbar icon text placement:", xalign=0.0)
        box.add(label)

        self._radio_below = Gtk.RadioButton.new_with_label_from_widget(
            None, "Below each icon")
        self._radio_beside = Gtk.RadioButton.new_with_label_from_widget(
            self._radio_below, "Beside each icon")

        if self.settings.toolbar_style == TOOLBAR_TEXT_BESIDE:
            self._radio_beside.set_active(True)
        else:
            self._radio_below.set_active(True)

        self._radio_below.connect("toggled", self._on_toolbar_style_toggled)
        self._radio_beside.connect("toggled", self._on_toolbar_style_toggled)

        box.add(self._radio_below)
        box.add(self._radio_beside)
        return box

    def _on_toolbar_style_toggled(self, _btn):
        style = (TOOLBAR_TEXT_BESIDE if self._radio_beside.get_active()
                 else TOOLBAR_TEXT_BELOW)
        self.settings.set_toolbar_style(style)
        self._on_apply()

    # ------------------------------------------------------- run/commit -- #
    def run_modal(self):
        """
        Show the dialog and handle Save/Cancel. On Save: persist to disk. On
        Cancel or window-close: restore the original values and re-apply (revert
        the preview). Either way the dialog is destroyed before returning.
        """
        response = self.run()
        if response == Gtk.ResponseType.OK:
            self.settings.save()
        else:
            # Restore snapshot and revert the live preview.
            o = self._original
            self.settings.set_editor_font(o["editor_font"])
            self.settings.set_code_font(o["code_font"])
            self.settings.set_preview_font(o["preview_font"])
            self.settings.set_editor_line_spacing(o["editor_line_spacing"])
            self.settings.set_preview_line_spacing(o["preview_line_spacing"])
            self.settings.set_toolbar_style(o["toolbar_style"])
            self._on_apply()
        self.destroy()

    # ----------------------------------------------------------- helper -- #
    @staticmethod
    def _label(text):
        lbl = Gtk.Label(label=text)
        lbl.set_xalign(0.0)
        return lbl
