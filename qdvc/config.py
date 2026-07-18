"""
config.py — shared constants and sentinels for QDVC Markdown Notebook.

This module has no GTK or filesystem dependencies, so it can be imported
freely from any layer.
"""

APP_NAME = "QDVC Markdown Notebook"

# Application identity, shared by both front-ends (spec §7.1/§7.2).
#   APP_ID    — the Gtk.Application / Adw.Application id ("qdvc.<App>").
#   PRGNAME   — the GLib program name → X11 WM_CLASS, matching the .desktop
#               StartupWMClass line.
#   STOCK_ICON_NAME — the default freedesktop themed icon name used when no
#               custom icon set is configured. Defined once here so both the
#               GTK3 and GTK4 front-ends (and settings.update_desktop_icon)
#               agree; each front-end re-exports it as ICON_NAME (spec §7.3).
APP_ID = "qdvc.MarkdownNotebook"
PRGNAME = "qdvc-markdown-notebook"
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
