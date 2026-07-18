#!/usr/bin/env python3
"""
qdvc_markdown_notebook.py

A three-pane markdown notebook viewer/editor for the MATE / GNOME2-era
desktop, built with GTK 3 via PyGObject.

Usage:
    python3 qdvc_markdown_notebook.py /path/to/markdown/data
    python3 qdvc_markdown_notebook.py        # start empty, open folder via Ctrl+O

This file is a thin entry point. Application logic lives in the qdvc
package: GTK-free core modules (config, model, settings, pango_markdown) and the
GTK3 view/controller modules (prefaced gtk3_). See MAINTENANCE.md.
"""

import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib  # noqa: E402

from qdvc.gtk3_window import NotebookWindow


def main():
    # Help the window manager associate our windows with the .desktop file by
    # giving the process a stable program name → WM_CLASS (#5). The .desktop
    # file should set "StartupWMClass=qdvc-markdown-notebook" to match.
    GLib.set_prgname("qdvc-markdown-notebook")

    # Set the default icon for all windows/dialogs so the panel/taskbar shows
    # the app icon rather than the generic window icon. This matches the Icon=
    # line in the .desktop file.
    Gtk.Window.set_default_icon_name("accessories-text-editor")

    root = sys.argv[1] if len(sys.argv) > 1 else None
    win = NotebookWindow(root_folder=root)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
