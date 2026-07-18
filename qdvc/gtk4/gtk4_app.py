"""
gtk4_app.py — the GTK 4 / libadwaita Adw.Application (spec §9).

Bootstraps the modern front-end:
  * ``GLib.set_prgname(...)`` at import so WM_CLASS matches the .desktop
    StartupWMClass (spec §7.2);
  * an ``Adw.Application`` (id ``qdvc.MarkdownNotebook``, ``HANDLES_OPEN``);
  * ``do_startup`` sets the app-wide default icon (spec §7.3);
  * accelerators registered via ``set_accels_for_action("win.<action>", [...])``
    from the shared ``ui_prefs.SHORTCUTS`` table (spec §10);
  * ``do_activate`` / ``do_open`` build/route the single main window.

``ICON_NAME`` mirrors gtk3_app.ICON_NAME (both re-export config.STOCK_ICON_NAME).
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, GLib  # noqa: E402

from ..config import APP_ID, PRGNAME, STOCK_ICON_NAME
from .. import ui_prefs
from .gtk4_window import NotebookWindow
from .gtk4_shortcuts import build_shortcuts_window

ICON_NAME = STOCK_ICON_NAME

GLib.set_prgname(PRGNAME)


class NotebookApp(Adw.Application):
    """The single-instance GTK 4 application."""

    def __init__(self):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self._window = None

    def do_startup(self):
        Adw.Application.do_startup(self)
        Gtk.Window.set_default_icon_name(ICON_NAME)
        self._register_accels()

    def _register_accels(self):
        """Register accelerators for win.* actions from the shared table."""
        for sc in ui_prefs.shortcuts_for(ui_prefs.SCOPE_GTK4):
            if not sc.accels:
                continue
            self.set_accels_for_action(f"win.{sc.action}", list(sc.accels))
        # The shortcuts window action is app-provided.
        self.set_accels_for_action("win.show-help-overlay",
                                   list(ui_prefs.accels_for("show-help-overlay")))

    def do_activate(self):
        self._ensure_window().present()

    def do_open(self, files, _n_files, _hint):
        win = self._ensure_window()
        if files:
            path = files[0].get_path()
            if path:
                win.open_folder(path)
        win.present()

    def _ensure_window(self):
        if self._window is None:
            self._window = NotebookWindow(application=self)
            # win.show-help-overlay opens the shared shortcuts window.
            help_action = Gio.SimpleAction.new("show-help-overlay", None)
            help_action.connect("activate", self._on_show_shortcuts)
            self._window.add_action(help_action)
        return self._window

    def _on_show_shortcuts(self, _action, _param):
        build_shortcuts_window(self._window).present()


def main(argv):
    """Entry point used by the backend dispatcher. `argv` includes argv[0]."""
    app = NotebookApp()
    return app.run(argv)
