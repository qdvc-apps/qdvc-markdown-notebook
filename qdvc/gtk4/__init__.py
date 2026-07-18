"""
qdvc.gtk4 — the GTK 4 / libadwaita front-end (parallel, GNOME HIG).

Every module here is prefaced ``gtk4_`` and imports GTK 4 + Adw. It follows the
GNOME Human Interface Guidelines and reuses the pure core unchanged; only the
view mechanics differ from the GTK 3 front-end. View modules reach the pure core
with ``from ..`` and siblings with ``from .gtk4_x``. See
docs/MAINTENANCE_GTK3_GTK4.md and the common spec §9.
"""

__all__ = [
    "gtk4_app", "gtk4_window", "gtk4_actions", "gtk4_preferences",
    "gtk4_shortcuts", "gtk4_editorview", "gtk4_highlighter",
]
