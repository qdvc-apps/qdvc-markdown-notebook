"""
gtk3_app.py — the GTK 3 Gtk.Application for QDVC Markdown Notebook.

Per the common spec §8, the GTK3 front-end is bootstrapped by a Gtk.Application
(id ``qdvc.MarkdownNotebook``, ``HANDLES_OPEN`` because a workspace folder may
be passed on the command line):

  * ``GLib.set_prgname(...)`` runs at import so the X11 WM_CLASS matches the
    ``.desktop`` StartupWMClass (spec §7.2);
  * ``do_startup`` sets the app-wide default icon (spec §7.3);
  * ``do_activate`` builds the single main window;
  * ``do_open`` routes a folder argument to a (new or existing) window.

The themed icon name is defined here once as ``ICON_NAME`` (re-exporting the
shared ``config.STOCK_ICON_NAME``) so it is trivial to override (spec §7.3).
"""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gio, GLib  # noqa: E402

from ..config import APP_ID, PRGNAME, STOCK_ICON_NAME
from .gtk3_window import NotebookWindow

# The default themed icon name (spec §7.3). Defined once here (and mirrored in
# gtk4_app.ICON_NAME) so overriding the app icon is a one-line change.
ICON_NAME = STOCK_ICON_NAME

# Load-bearing: matches the .desktop StartupWMClass so the panel associates the
# running window with its launcher (spec §7.2). Set at import.
GLib.set_prgname(PRGNAME)


class NotebookApp(Gtk.Application):
    """The single-instance GTK3 application."""

    def __init__(self):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self._window = None

    def do_startup(self):
        Gtk.Application.do_startup(self)
        # App-wide default icon so dialogs and the panel/taskbar show it before
        # any .desktop matching (spec §7.3).
        Gtk.Window.set_default_icon_name(ICON_NAME)

    def do_activate(self):
        # Launched with no folder argument: show the main window (creating it
        # once; subsequent activations just present it).
        win = self._ensure_window()
        win.present()

    def do_open(self, files, _n_files, _hint):
        # Launched with a folder argument (HANDLES_OPEN). Use the first path as
        # the workspace folder.
        win = self._ensure_window()
        if files:
            path = files[0].get_path()
            if path:
                win.open_folder(path)
        win.present()

    def _ensure_window(self, root_folder=None):
        if self._window is None:
            self._window = NotebookWindow(root_folder=root_folder,
                                          application=self)
            self._window.show_all()
        return self._window


def main(argv):
    """Entry point used by the backend dispatcher. `argv` includes argv[0]."""
    app = NotebookApp()
    return app.run(argv)
