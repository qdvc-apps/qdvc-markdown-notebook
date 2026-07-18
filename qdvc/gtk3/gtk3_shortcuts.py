"""
gtk3_shortcuts.py — wire the shared ui_prefs.SHORTCUTS table into GTK 3.

Per the common spec §10, the keyboard-shortcut set is defined once in the pure
layer (``qdvc.ui_prefs.SHORTCUTS``) and both front-ends are driven from it. In
GTK 3 shortcuts are menubar-driven: accelerators are attached to menu items via
a ``Gtk.AccelGroup`` and shown next to their labels. This module provides the
helpers the menubar uses so the concrete ``Gdk.KEY_*`` / modifier values are
never hard-coded there — they are parsed from the shared table's accel strings.

Window-level bindings that are not menu items (Ctrl+Tab / Ctrl+Shift+Tab and
Alt+1..9 tab switching) are handled directly in the window's key-press handler;
their canonical accelerators still live in the shared table for the shortcuts
reference, and ``verify_window_accels`` cross-checks them.
"""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from .. import ui_prefs


def parse_accel(action):
    """
    Return ``(keyval, modifiers)`` for an action's primary accelerator by
    parsing its accel string from the shared table, or ``(0, 0)`` when the
    action has no accelerator (or cannot be parsed).
    """
    accel = ui_prefs.accel_for(action)
    if not accel:
        return (0, 0)
    keyval, mods = Gtk.accelerator_parse(accel)
    return (keyval, mods)


def add_menu_accel(item, accel_group, action, signal="activate"):
    """
    Attach the accelerator for `action` (from the shared table) to a menu
    `item`, shown next to its label (``AccelFlags.VISIBLE``). No-op when the
    action has no accelerator. Returns the item for chaining.
    """
    keyval, mods = parse_accel(action)
    if keyval:
        item.add_accelerator(signal, accel_group, keyval, mods,
                             Gtk.AccelFlags.VISIBLE)
    return item


def verify_window_accels():
    """
    Sanity check used by tests / smoke checks: confirm the window-level
    (non-menu) actions the window handles by hand still exist in the shared
    table, so the two never drift. Returns a list of missing action ids
    (empty when consistent).
    """
    expected = ("next-tab", "prev-tab", "goto-tab")
    return [a for a in expected if ui_prefs.shortcut(a) is None]
