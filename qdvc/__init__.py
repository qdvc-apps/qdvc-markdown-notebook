"""
qdvc — internal package for QDVC Markdown Notebook.

The package is split into two layers so the GTK4 view can reuse the lower
layer unchanged:

GTK-free core (data / application logic, no GTK import — unit-testable headless):
    config          Constants and shared sentinels.
    model           Data layer: notes + file I/O + slug/rename + outline parse.
    settings        Persistent user settings (YAML under ~/.config) + the
                    icon-set / .desktop install helpers. This is the *data/model*
                    side of preferences — what gets stored and loaded.
    pango_markdown  Markdown → Pango-markup string renderer for preview mode.
                    (Pango markup is a stable string format, not a GTK widget.)
    strings         All user-facing UI text, in one place for future translation
                    (no GTK). The gtk3_ modules import their labels/messages from
                    here instead of hard-coding literals.

GTK3 view / controller (nested sub-package ``qdvc.gtk3``; every module prefaced
``gtk3_``):
    gtk3_app          NotebookApp: the Gtk.Application (id, icon, prgname).
    gtk3_highlighter  MarkdownHighlighter (GTK TextBuffer tagging).
    gtk3_editortab    EditorTab: one tab's editor widget + per-tab state.
    gtk3_preferences  PreferencesDialog: the *view/controller* for settings —
                      the window that lets the user edit what settings.py stores.
    gtk3_menubar      MenuBarMixin: the window's menu bar.
    gtk3_toolbar      ToolbarMixin: the window's toolbar + styling.
    gtk3_panes        PanesMixin: the four panes + their data binding.
    gtk3_actions      ActionsMixin: user-action handlers, context menus, dialogs.
    gtk3_window       NotebookWindow: the top-level window that composes the
                      mixins above (view + controller core).
    gtk3_shortcuts    Wires the shared ui_prefs.SHORTCUTS table into the GTK3
                      accelerators / mnemonics.

GTK4 / libadwaita view (nested sub-package ``qdvc.gtk4``; every module prefaced
``gtk4_``): gtk4_app, gtk4_window, gtk4_actions, gtk4_preferences,
gtk4_shortcuts, plus editor/preview/highlighter helpers. Follows the GNOME HIG
and reuses the pure core unchanged (spec §9).

Pure UI helpers shared by both front-ends (no GTK):
    ui_prefs        SHORTCUTS table (single source of truth for keybindings,
                    spec §10) + toolkit-independent UI helpers.
    platform_utils  Launch system apps (viewer, editor, file manager; spec §11).

Note the deliberate pairing: ``settings`` (model) ↔ ``gtk3_preferences`` /
``gtk4_preferences`` (views).
"""

from .config import APP_ID, APP_NAME  # noqa: F401  (re-export)

__version__ = "0.1.0"

__all__ = [
    "APP_ID", "APP_NAME", "__version__",
    # GTK-free core
    "config", "model", "settings", "pango_markdown", "strings",
    "ui_prefs", "platform_utils",
]
