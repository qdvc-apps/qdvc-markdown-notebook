#!/usr/bin/env python3
"""
qdvc_markdown_notebook.py

A three-pane markdown notebook viewer/editor for the Linux desktop, with a
GTK 3 / MATE-era front-end (default) and a parallel GTK 4 / libadwaita
front-end.

Usage:
    python3 qdvc_markdown_notebook.py /path/to/markdown/data
    python3 qdvc_markdown_notebook.py                 # empty; open via Ctrl+O
    python3 qdvc_markdown_notebook.py --gtk4 [folder]  # force the GTK4 front-end
    python3 qdvc_markdown_notebook.py --gtk3 [folder]  # force the GTK3 front-end

This file is a THIN DISPATCHER (spec section 3): it selects the UI toolkit
*before* importing any GTK, so only the chosen front-end is loaded. Backend
selection order:

    1. an explicit --gtk3 / --gtk4 flag (consumed wherever it appears in argv);
    2. the `ui_backend` key saved in the config;
    3. the default, gtk3.

If the GTK 4 front-end fails to import (e.g. libadwaita absent) it prints a note
to stderr and falls back to GTK 3. All application logic lives in the `qdvc`
package: a GTK-free pure core plus the `qdvc.gtk3` / `qdvc.gtk4` view
sub-packages. See docs/MAINTENANCE.md.
"""

import sys

from qdvc.settings import (
    Settings, UI_BACKEND_GTK3, UI_BACKEND_GTK4,
)


def _select_backend(argv):
    """
    Resolve the backend and return (backend, remaining_argv) where the flag has
    been stripped. `argv` includes argv[0]. The flag wins over config; config
    wins over the default.
    """
    backend = None
    remaining = [argv[0]] if argv else ["qdvc_markdown_notebook.py"]
    for arg in argv[1:]:
        if arg == "--gtk3":
            backend = UI_BACKEND_GTK3
        elif arg == "--gtk4":
            backend = UI_BACKEND_GTK4
        else:
            remaining.append(arg)
    if backend is None:
        # Fall back to the stored preference (validated), else the default.
        backend = Settings.load().ui_backend
    return backend, remaining


def main():
    backend, argv = _select_backend(sys.argv)

    if backend == UI_BACKEND_GTK4:
        try:
            from qdvc.gtk4 import gtk4_app as app_module
        except Exception as exc:  # ImportError, or a missing typelib at import
            sys.stderr.write(
                f"qdvc-markdown-notebook: GTK 4 front-end unavailable "
                f"({exc}); falling back to GTK 3.\n")
            from qdvc.gtk3 import gtk3_app as app_module
    else:
        from qdvc.gtk3 import gtk3_app as app_module

    return app_module.main(argv)


if __name__ == "__main__":
    sys.exit(main())
