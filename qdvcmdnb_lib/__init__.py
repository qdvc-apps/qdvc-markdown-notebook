"""
qdvcmdnb_lib — internal package for QDVC Markdown Notebook.

Modules:
    config       Constants and shared sentinels.
    settings     Persistent user settings (YAML under ~/.config). No GTK.
    model        Pure-Python data layer (no GTK): notes + file I/O.
    highlighter  MarkdownHighlighter (GTK TextBuffer tagging).
    editortab    EditorTab: one tab's editor widget + per-tab state.
    window       NotebookWindow (view + controller).
"""

__all__ = ["config", "settings", "model", "highlighter", "editortab", "window"]
