"""
qdvc — internal package for QDVC Markdown Notebook.

The package is split into two layers so a future GTK4 view could reuse the lower
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

GTK3 view / controller (all modules prefaced ``gtk3_``; replace these for a
different toolkit, e.g. a future ``gtk4_`` set):
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

Note the deliberate pairing: ``settings`` (model) ↔ ``gtk3_preferences`` (view).
"""

__all__ = [
    # GTK-free core
    "config", "model", "settings", "pango_markdown", "strings",
    # GTK3 view/controller
    "gtk3_highlighter", "gtk3_editortab", "gtk3_preferences",
    "gtk3_menubar", "gtk3_toolbar", "gtk3_panes", "gtk3_actions",
    "gtk3_window",
]
