"""
qdvcmdnb_lib — internal package for QDVC Markdown Notebook.

Modules:
    config       Constants and shared sentinels.
    settings     Persistent user settings (YAML under ~/.config). No GTK.
    model        Pure-Python data layer (no GTK): notes + file I/O + slug/rename.
    highlighter  MarkdownHighlighter (GTK TextBuffer tagging).
    editortab    EditorTab: one tab's editor widget + per-tab state.
    preferences  PreferencesDialog: fonts + toolbar style.
    window       NotebookWindow (view + controller).
"""

__all__ = ["config", "settings", "model", "highlighter", "editortab",
           "preferences", "window"]
