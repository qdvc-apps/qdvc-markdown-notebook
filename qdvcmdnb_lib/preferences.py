"""
preferences.py — the Preferences dialog for QDVC Markdown Notebook.

In the GNOME2 / MATE idiom this is "Preferences" (under the Edit menu). It lets
the user pick the editor font, the code font, and whether toolbar buttons show
their text beside or below the icon.

Behaviour: changes preview live in the editor while the dialog is open. The
dialog has Save and Cancel buttons — Save persists the settings to disk; Cancel
(or closing the window) restores the values that were in effect when the dialog
opened and re-applies them, discarding the preview.
"""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from .settings import TOOLBAR_TEXT_BESIDE, TOOLBAR_TEXT_BELOW


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
            "toolbar_style": settings.toolbar_style,
        }

        self.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        self.add_button("_Save", Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)
        self.set_default_size(420, -1)

        content = self.get_content_area()
        content.set_spacing(12)
        content.set_border_width(12)
        content.add(self._build_fonts_section())
        content.add(self._build_toolbar_section())

        self.show_all()

    # ------------------------------------------------------------ fonts -- #
    def _build_fonts_section(self):
        frame = Gtk.Frame(label="Fonts")
        grid = Gtk.Grid(row_spacing=6, column_spacing=12)
        grid.set_border_width(8)

        grid.attach(self._label("Editor font:"), 0, 0, 1, 1)
        self.editor_font_btn = Gtk.FontButton()
        self.editor_font_btn.set_font(self.settings.editor_font)
        self.editor_font_btn.set_hexpand(True)
        self.editor_font_btn.connect("font-set", self._on_editor_font_set)
        grid.attach(self.editor_font_btn, 1, 0, 1, 1)

        grid.attach(self._label("Code font:"), 0, 1, 1, 1)
        self.code_font_btn = Gtk.FontButton()
        self.code_font_btn.set_font(self.settings.code_font)
        self.code_font_btn.set_hexpand(True)
        self.code_font_btn.connect("font-set", self._on_code_font_set)
        grid.attach(self.code_font_btn, 1, 1, 1, 1)

        frame.add(grid)
        return frame

    def _on_editor_font_set(self, btn):
        # Live preview only — not persisted until Save.
        self.settings.set_editor_font(btn.get_font())
        self._on_apply()

    def _on_code_font_set(self, btn):
        self.settings.set_code_font(btn.get_font())
        self._on_apply()

    # ---------------------------------------------------------- toolbar -- #
    def _build_toolbar_section(self):
        frame = Gtk.Frame(label="Toolbar")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_border_width(8)

        label = Gtk.Label(label="Icon text placement:", xalign=0.0)
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

        frame.add(box)
        return frame

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
            self.settings.set_editor_font(self._original["editor_font"])
            self.settings.set_code_font(self._original["code_font"])
            self.settings.set_toolbar_style(self._original["toolbar_style"])
            self._on_apply()
        self.destroy()

    # ----------------------------------------------------------- helper -- #
    @staticmethod
    def _label(text):
        lbl = Gtk.Label(label=text)
        lbl.set_xalign(0.0)
        return lbl
