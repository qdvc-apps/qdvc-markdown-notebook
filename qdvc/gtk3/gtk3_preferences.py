"""
gtk3_preferences.py — the Preferences dialog for QDVC Markdown Notebook (GTK3).

This is the *view* for the settings model (qdvc.settings): the window
that lets the user edit what settings.py stores. In the GNOME2 / MATE idiom this
is "Preferences" (under the Edit menu). It is a tabbed dialog:

  * Fonts     — editor font, code font, markdown-preview font, and the editor /
                preview line spacing.
  * Interface — toolbar button text placement (beside vs below the icon), the
                tab-title length, a custom application icon set, and the
                session/sort persistence options.

Behaviour: changes preview live in the app while the dialog is open. The dialog
has Save and Cancel buttons — Save persists the settings to disk; Cancel (or
closing the window) restores the values that were in effect when the dialog
opened and re-applies them, discarding the live preview.

User-facing text comes from qdvc.strings (Prefs / Dialog namespaces).
"""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from ..settings import (
    TOOLBAR_TEXT_BESIDE,
    TOOLBAR_TEXT_BELOW,
    MIN_LINE_SPACING,
    MAX_LINE_SPACING,
    MIN_TAB_TITLE_LENGTH,
    MAX_TAB_TITLE_LENGTH,
)
from ..strings import Prefs as P, Dialog as D


class PreferencesDialog(Gtk.Dialog):

    def __init__(self, parent, settings, on_apply):
        # A Gtk.Dialog is a top-level window with a content area plus an action
        # area for buttons. transient_for ties it to the main window (so the WM
        # keeps it on top and centred); modal blocks the rest of the app while
        # open. The actual rows live in a Gtk.Notebook (tabbed pages) added to
        # the dialog's content area (get_content_area()).
        super().__init__(title=P.TITLE, transient_for=parent, modal=True)
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
            "tab_title_length": settings.tab_title_length,
            "remember_sort": settings.remember_sort,
            "restore_session": settings.restore_session,
            "icon_set_dir": settings.icon_set_dir,
        }

        # add_button pairs a label with a response code that run() returns.
        self.add_button(D.BTN_CANCEL, Gtk.ResponseType.CANCEL)
        self.add_button(D.BTN_SAVE, Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)
        self.set_default_size(460, -1)

        # append_page(child, tab_label) adds a notebook tab.
        notebook = Gtk.Notebook()
        notebook.set_border_width(8)
        notebook.append_page(self._build_fonts_tab(),
                             Gtk.Label(label=P.TAB_FONTS))
        notebook.append_page(self._build_interface_tab(),
                             Gtk.Label(label=P.TAB_INTERFACE))

        content = self.get_content_area()
        content.set_spacing(12)
        content.set_border_width(8)
        content.add(notebook)

        # show_all realizes and reveals the dialog and all its children at once.
        self.show_all()

    # -------------------------------------------------------- Fonts tab -- #
    def _build_fonts_tab(self):
        # Lay the font controls out in a Gtk.Grid (rows × columns).
        # grid.attach(child, col, row, width, height) places each widget; we use
        # column 0 for labels and column 1 for the controls. A Gtk.FontButton
        # opens the system font picker and fires "font-set" when a font is
        # chosen; get_font() returns its description string.
        grid = Gtk.Grid(row_spacing=8, column_spacing=12)
        grid.set_border_width(12)

        row = 0
        grid.attach(self._label(P.EDITOR_FONT), 0, row, 1, 1)
        self.editor_font_btn = Gtk.FontButton()
        self.editor_font_btn.set_font(self.settings.editor_font)
        self.editor_font_btn.set_hexpand(True)
        self.editor_font_btn.connect("font-set", self._on_editor_font_set)
        grid.attach(self.editor_font_btn, 1, row, 1, 1)

        row += 1
        grid.attach(self._label(P.CODE_FONT), 0, row, 1, 1)
        self.code_font_btn = Gtk.FontButton()
        self.code_font_btn.set_font(self.settings.code_font)
        self.code_font_btn.set_hexpand(True)
        self.code_font_btn.connect("font-set", self._on_code_font_set)
        grid.attach(self.code_font_btn, 1, row, 1, 1)

        row += 1
        grid.attach(self._label(P.PREVIEW_FONT), 0, row, 1, 1)
        self.preview_font_btn = Gtk.FontButton()
        self.preview_font_btn.set_font(self.settings.preview_font)
        self.preview_font_btn.set_hexpand(True)
        self.preview_font_btn.connect("font-set", self._on_preview_font_set)
        grid.attach(self.preview_font_btn, 1, row, 1, 1)

        row += 1
        grid.attach(self._label(P.EDITOR_LINE_SPACING), 0, row, 1, 1)
        self.editor_spacing_spin = self._spacing_spin(
            self.settings.editor_line_spacing, self._on_editor_spacing_changed)
        grid.attach(self.editor_spacing_spin, 1, row, 1, 1)

        row += 1
        grid.attach(self._label(P.PREVIEW_LINE_SPACING), 0, row, 1, 1)
        self.preview_spacing_spin = self._spacing_spin(
            self.settings.preview_line_spacing,
            self._on_preview_spacing_changed)
        grid.attach(self.preview_spacing_spin, 1, row, 1, 1)

        return grid

    def _spacing_spin(self, value, handler):
        # A Gtk.SpinButton is a number entry with up/down steppers.
        # new_with_range(min, max, step) bounds it; "value-changed" fires on any
        # change; halign START keeps it from stretching across the cell.
        spin = Gtk.SpinButton.new_with_range(
            MIN_LINE_SPACING, MAX_LINE_SPACING, 1)
        spin.set_value(value)
        spin.set_halign(Gtk.Align.START)
        spin.connect("value-changed", handler)
        return spin

    def _on_editor_font_set(self, btn):
        # "font-set" handler: push the new font into settings (in memory only)
        # and call _on_apply so the window re-themes immediately. Live preview
        # only — not persisted until Save.
        self.settings.set_editor_font(btn.get_font())
        self._on_apply()

    def _on_code_font_set(self, btn):
        # As above, for the code font.
        self.settings.set_code_font(btn.get_font())
        self._on_apply()

    def _on_preview_font_set(self, btn):
        # As above, for the preview body font.
        self.settings.set_preview_font(btn.get_font())
        self._on_apply()

    def _on_editor_spacing_changed(self, spin):
        # SpinButton "value-changed": get_value_as_int() reads the integer value.
        self.settings.set_editor_line_spacing(spin.get_value_as_int())
        self._on_apply()

    def _on_preview_spacing_changed(self, spin):
        # As above, for the preview spacing.
        self.settings.set_preview_line_spacing(spin.get_value_as_int())
        self._on_apply()

    # ---------------------------------------------------- Interface tab -- #
    def _build_interface_tab(self):
        # A vertical Gtk.Box stacks the interface controls, with horizontal
        # Gtk.Separators drawing divider lines between groups. Sub-groups use
        # nested boxes. xalign=0.0 left-aligns a label within its allocation.
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_border_width(12)

        # --- toolbar icon text placement ---
        tb_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        tb_box.add(Gtk.Label(label=P.TOOLBAR_TEXT_PLACEMENT, xalign=0.0))

        # RadioButtons in one group: new_with_label_from_widget(None, ...) starts
        # the group; passing the first button as the "group" widget joins it, so
        # exactly one can be active. We pre-select the one matching settings.
        self._radio_below = Gtk.RadioButton.new_with_label_from_widget(
            None, P.TOOLBAR_TEXT_BELOW)
        self._radio_beside = Gtk.RadioButton.new_with_label_from_widget(
            self._radio_below, P.TOOLBAR_TEXT_BESIDE)

        if self.settings.toolbar_style == TOOLBAR_TEXT_BESIDE:
            self._radio_beside.set_active(True)
        else:
            self._radio_below.set_active(True)

        self._radio_below.connect("toggled", self._on_toolbar_style_toggled)
        self._radio_beside.connect("toggled", self._on_toolbar_style_toggled)
        tb_box.add(self._radio_below)
        tb_box.add(self._radio_beside)
        box.add(tb_box)

        box.add(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # --- tab title length ---
        tab_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        tab_row.add(self._label(P.TAB_TITLE_LENGTH))
        self.tab_title_spin = Gtk.SpinButton.new_with_range(
            MIN_TAB_TITLE_LENGTH, MAX_TAB_TITLE_LENGTH, 1)
        self.tab_title_spin.set_value(self.settings.tab_title_length)
        self.tab_title_spin.set_halign(Gtk.Align.START)
        self.tab_title_spin.connect("value-changed",
                                    self._on_tab_title_length_changed)
        tab_row.add(self.tab_title_spin)
        box.add(tab_row)

        box.add(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # --- session / sort persistence ---
        # Gtk.CheckButton is a labelled tick box; set_active sets its state and
        # "toggled" fires on change.
        self.chk_remember_sort = Gtk.CheckButton(label=P.REMEMBER_SORT)
        self.chk_remember_sort.set_active(self.settings.remember_sort)
        self.chk_remember_sort.connect("toggled",
                                       self._on_remember_sort_toggled)
        box.add(self.chk_remember_sort)

        self.chk_restore_session = Gtk.CheckButton(label=P.RESTORE_SESSION)
        self.chk_restore_session.set_active(self.settings.restore_session)
        self.chk_restore_session.connect("toggled",
                                         self._on_restore_session_toggled)
        box.add(self.chk_restore_session)

        box.add(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # --- custom icon set ---
        # A Gtk.FileChooserButton in SELECT_FOLDER mode shows the chosen folder
        # and pops up a picker; "file-set" fires once a folder is chosen.
        icon_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        icon_box.add(Gtk.Label(label=P.ICON_SET_LABEL, xalign=0.0))
        chooser_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.icon_set_chooser = Gtk.FileChooserButton(
            title=P.ICON_SET_CHOOSER_TITLE,
            action=Gtk.FileChooserAction.SELECT_FOLDER)
        self.icon_set_chooser.set_hexpand(True)
        if self.settings.icon_set_dir:
            self.icon_set_chooser.set_filename(self.settings.icon_set_dir)
        self.icon_set_chooser.connect("file-set", self._on_icon_set_chosen)
        chooser_row.pack_start(self.icon_set_chooser, True, True, 0)

        clear_btn = Gtk.Button(label=P.ICON_SET_CLEAR)
        clear_btn.set_tooltip_text(P.ICON_SET_CLEAR_TIP)
        clear_btn.connect("clicked", self._on_icon_set_cleared)
        chooser_row.pack_start(clear_btn, False, False, 0)
        icon_box.add(chooser_row)

        # A wrapped, small-print hint. set_markup interprets the <small> tag.
        hint = Gtk.Label(xalign=0.0)
        hint.set_markup(f"<small>{P.ICON_SET_HINT}</small>")
        hint.set_line_wrap(True)
        icon_box.add(hint)
        box.add(icon_box)

        return box

    def _on_toolbar_style_toggled(self, _btn):
        # Either radio firing "toggled" lands here; we read whichever is active
        # and store the matching style, then live-apply.
        style = (TOOLBAR_TEXT_BESIDE if self._radio_beside.get_active()
                 else TOOLBAR_TEXT_BELOW)
        self.settings.set_toolbar_style(style)
        self._on_apply()

    def _on_tab_title_length_changed(self, spin):
        # SpinButton change → store the new tab-title length and live-apply.
        self.settings.set_tab_title_length(spin.get_value_as_int())
        self._on_apply()

    def _on_remember_sort_toggled(self, btn):
        # CheckButton change → store the boolean and live-apply.
        self.settings.set_remember_sort(btn.get_active())
        self._on_apply()

    def _on_restore_session_toggled(self, btn):
        # As above, for the restore-session option.
        self.settings.set_restore_session(btn.get_active())
        self._on_apply()

    def _on_icon_set_chosen(self, chooser):
        # "file-set" → store the chosen folder path (get_filename); empty string
        # means "no custom set". Live-apply so the icon updates immediately.
        self.settings.set_icon_set_dir(chooser.get_filename() or "")
        self._on_apply()

    def _on_icon_set_cleared(self, _btn):
        # Clear button → drop the custom icon set. unselect_all empties the
        # chooser's displayed selection.
        self.settings.set_icon_set_dir("")
        self.icon_set_chooser.unselect_all()
        self._on_apply()

    # ------------------------------------------------------- run/commit -- #
    def run_modal(self):
        """
        Show the dialog and handle Save/Cancel. run() blocks until the user
        responds and returns the response code of the button they clicked (or a
        cancel/close code). On Save: persist to disk. On Cancel or window-close:
        restore the original values and re-apply (revert the preview). Either way
        the dialog is destroyed before returning.
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
            self.settings.set_tab_title_length(o["tab_title_length"])
            self.settings.set_remember_sort(o["remember_sort"])
            self.settings.set_restore_session(o["restore_session"])
            self.settings.set_icon_set_dir(o["icon_set_dir"])
            self._on_apply()
        self.destroy()

    # ----------------------------------------------------------- helper -- #
    @staticmethod
    def _label(text):
        # Small helper: a left-aligned Gtk.Label (set_xalign(0.0) = left edge).
        lbl = Gtk.Label(label=text)
        lbl.set_xalign(0.0)
        return lbl
