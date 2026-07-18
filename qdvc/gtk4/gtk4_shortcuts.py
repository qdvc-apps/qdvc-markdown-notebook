"""
gtk4_shortcuts.py — the GTK 4 keyboard-shortcuts window.

Per the common spec §10, the shortcuts window is built from the same pure
``qdvc.ui_prefs.SHORTCUTS`` table that drives the GTK 3 accelerators, so the two
front-ends never drift. The application (gtk4_app) separately registers the
accelerators with ``set_accels_for_action``; this module only presents them.
"""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from .. import ui_prefs


def build_shortcuts_window(parent):
    """
    Build and return a ``Gtk.ShortcutsWindow`` populated from the shared table
    (GTK4-scope entries), grouped by their group heading.
    """
    win = Gtk.ShortcutsWindow(transient_for=parent, modal=True)
    section = Gtk.ShortcutsSection(section_name="main", visible=True)

    for group_name, shortcuts in ui_prefs.grouped_shortcuts(ui_prefs.SCOPE_GTK4):
        group = Gtk.ShortcutsGroup(title=group_name)
        for sc in shortcuts:
            # A shortcut with several accels (e.g. Alt+1..9) is shown with its
            # first accel plus the label describing the range.
            accel = " ".join(sc.accels)
            item = Gtk.ShortcutsShortcut(title=sc.label, accelerator=accel)
            group.add_shortcut(item)
        section.add_group(group)

    win.add_section(section)
    return win
