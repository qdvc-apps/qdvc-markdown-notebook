"""
config.py — shared constants and sentinels for QDVC Markdown Notebook.

This module has no GTK or filesystem dependencies, so it can be imported
freely from any layer.
"""

APP_NAME = "QDVC Markdown Notebook"

# Application identity, shared by both front-ends (spec §7.1/§7.2).
#   APP_ID    — the Gtk.Application / Adw.Application id ("qdvc.<App>"). It is
#               also the name of the .desktop file (qdvc.MarkdownNotebook.desktop)
#               so GNOME Shell on Wayland, which matches windows to launchers by
#               application id, pairs the running window with its launcher.
#   PRGNAME   — the GLib program name → X11 WM_CLASS, matching the .desktop
#               StartupWMClass line.
#   BUNDLED_ICON_NAME — the app's own icon, shipped in data/icons (a hicolor
#               theme root; regenerate with tools/make_icon.py) and installed into
#               the user's icon theme by scripts/build-app.sh. Named after APP_ID,
#               per the freedesktop convention.
#   STOCK_ICON_NAME — the freedesktop themed icon used when the bundled icon
#               cannot be found (spec §7.3: the app never *requires* a bundled
#               image). Both front-ends resolve between the two once at startup
#               (gtk3_app / gtk4_app resolve_icon_name), and
#               settings.default_icon_name() makes the same choice for the
#               .desktop Icon= line.
APP_ID = "qdvc.MarkdownNotebook"
PRGNAME = "qdvc-markdown-notebook"
BUNDLED_ICON_NAME = APP_ID
STOCK_ICON_NAME = "accessories-text-editor"

# Filename extensions treated as markdown notes.
MARKDOWN_EXTENSIONS = (".md", ".markdown", ".mdown", ".mkd", ".txt")

# Sort modes for the note list.
SORT_ALPHA = "alpha"
SORT_DATE_NEW = "date_new"
SORT_DATE_OLD = "date_old"

# Sentinel object representing the "All Notes" virtual folder in the sidebar.
# Compare with `is`, never `==`.
ALL_NOTES = object()

# Sidebar node kinds. Each sidebar row carries one of these so the selection
# handler knows what the row represents (stored in a hidden TreeStore column).
NODE_ALL_NOTES = "all_notes"        # every note under the root
NODE_INBOX = "inbox"                # notes at the top level only (not recursive)
NODE_EMPTY_NOTES = "empty_notes"    # notes that are empty / all-whitespace
NODE_SUBFOLDERS = "subfolders"      # the parent "Subfolders" row (no note list)
NODE_SUBFOLDER = "subfolder"        # an individual subfolder (label = its name)
