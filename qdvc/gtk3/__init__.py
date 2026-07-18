"""
qdvc.gtk3 — the GTK 3 / PyGObject front-end (primary, MATE/GNOME2-era look).

Every module here is prefaced ``gtk3_`` and imports GTK. View modules reach the
pure core with ``from ..`` (e.g. ``from ..model import ...``) and reach siblings
with ``from .gtk3_x``. See docs/MAINTENANCE.md and the common spec §8.
"""

__all__ = [
    "gtk3_app", "gtk3_window", "gtk3_menubar", "gtk3_toolbar", "gtk3_panes",
    "gtk3_actions", "gtk3_editortab", "gtk3_preferences", "gtk3_highlighter",
    "gtk3_shortcuts",
]
