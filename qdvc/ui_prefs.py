"""
ui_prefs.py — toolkit-independent UI helpers shared by BOTH front-ends.

This is a PURE module: it imports no GTK and is unit-testable headless. Per the
common spec (§10, §14) the keyboard-shortcut set is defined here, once, as the
single source of truth; the GTK3 and GTK4 front-ends are both driven from it so
they stay consistent.

The accelerators are expressed as GTK "accel strings" (the format understood by
``Gtk.accelerator_parse`` and ``Gtk.Application.set_accels_for_action``), e.g.
``"<Primary>s"`` for Ctrl+S. ``<Primary>`` maps to Ctrl on X11/Wayland and Cmd
on macOS, so the same table serves every platform.

Each entry is a ``Shortcut`` describing one command:

    action      a stable identifier for the command (also the GTK4 ``win.<id>``
                action name);
    label       the human-readable label (for a shortcuts window / menu);
    accels      tuple of accel strings (usually one; a couple bind two);
    scope       one of SCOPE_BOTH / SCOPE_GTK3 / SCOPE_GTK4 — where the shortcut
                is meaningful. Toolkit-specific entries are marked so neither
                front-end invents artificial parity (spec §10).
    group       a heading used to group entries in a shortcuts window.

Front-ends read ``SHORTCUTS`` (and the helpers below) rather than hard-coding
keys. ``accel_for(action)`` returns the primary accel string for an action, and
``shortcuts_for(scope)`` filters the table for a given toolkit.
"""

# Scope markers.
SCOPE_BOTH = "both"
SCOPE_GTK3 = "gtk3"
SCOPE_GTK4 = "gtk4"

# Group headings (used by the GTK4 shortcuts window and any GTK3 help view).
GROUP_FILE = "File"
GROUP_NOTE = "Note"
GROUP_VIEW = "View"
GROUP_TABS = "Tabs"
GROUP_APP = "Application"


class Shortcut:
    """One keyboard shortcut / command binding (pure data)."""

    __slots__ = ("action", "label", "accels", "scope", "group")

    def __init__(self, action, label, accels, scope=SCOPE_BOTH,
                 group=GROUP_APP):
        # Normalise a single accel string to a one-tuple.
        if isinstance(accels, str):
            accels = (accels,)
        self.action = action
        self.label = label
        self.accels = tuple(accels)
        self.scope = scope
        self.group = group

    def __repr__(self):  # pragma: no cover - debugging aid
        return (f"Shortcut(action={self.action!r}, accels={self.accels!r}, "
                f"scope={self.scope!r})")


# The canonical shortcut table. Kept in menu/command order. Accelerators mirror
# the GTK3 menubar exactly (see qdvc/gtk3/gtk3_menubar.py) and use the family
# defaults from the spec (§10): Ctrl+O open, Ctrl+Q quit, Alt+1..9 tab switch.
SHORTCUTS = (
    # ---- File ----
    Shortcut("new-note", "New note", "<Primary>n",
             SCOPE_BOTH, GROUP_NOTE),
    Shortcut("save-note", "Save note", "<Primary>s",
             SCOPE_BOTH, GROUP_NOTE),
    Shortcut("refresh-note", "Refresh note (reload from disk)", "<Primary>r",
             SCOPE_BOTH, GROUP_NOTE),
    Shortcut("open-workspace", "Open workspace", "<Primary>o",
             SCOPE_BOTH, GROUP_FILE),
    Shortcut("refresh-workspace", "Refresh workspace", "<Primary><Shift>r",
             SCOPE_BOTH, GROUP_FILE),
    Shortcut("new-tab", "New tab", "<Primary>t",
             SCOPE_BOTH, GROUP_TABS),
    Shortcut("close-tab", "Close tab", "<Primary>w",
             SCOPE_BOTH, GROUP_TABS),
    Shortcut("quit", "Quit", "<Primary>q",
             SCOPE_BOTH, GROUP_APP),
    # ---- Edit ----
    Shortcut("preferences", "Preferences", "<Primary>comma",
             SCOPE_BOTH, GROUP_APP),
    # ---- View toggles ----
    Shortcut("toggle-read-only", "Toggle read-only", "<Primary>e",
             SCOPE_BOTH, GROUP_VIEW),
    Shortcut("toggle-card-view", "Toggle card view", "<Primary>d",
             SCOPE_BOTH, GROUP_VIEW),
    Shortcut("toggle-preview", "Toggle rendered preview", "<Primary>grave",
             SCOPE_BOTH, GROUP_VIEW),
    Shortcut("toggle-outline", "Toggle headings outline", "<Primary><Shift>o",
             SCOPE_BOTH, GROUP_VIEW),
    # ---- Tab navigation ----
    Shortcut("next-tab", "Next tab", "<Primary>Tab",
             SCOPE_BOTH, GROUP_TABS),
    Shortcut("prev-tab", "Previous tab", "<Primary><Shift>Tab",
             SCOPE_BOTH, GROUP_TABS),
    # Alt+1..9 jump to a tab. Represented as a single logical entry; the
    # front-ends expand it to the nine concrete accelerators.
    Shortcut("goto-tab", "Jump to tab 1–9",
             ("<Alt>1", "<Alt>2", "<Alt>3", "<Alt>4", "<Alt>5",
              "<Alt>6", "<Alt>7", "<Alt>8", "<Alt>9"),
             SCOPE_BOTH, GROUP_TABS),
    # ---- Help ----
    Shortcut("about", "About", (), SCOPE_BOTH, GROUP_APP),
    # GTK4 provides a standard keyboard-shortcuts window; GTK3 does not.
    Shortcut("show-help-overlay", "Keyboard shortcuts", "<Primary>question",
             SCOPE_GTK4, GROUP_APP),
)


# Convenience index: action -> Shortcut.
_BY_ACTION = {s.action: s for s in SHORTCUTS}


def shortcut(action):
    """Return the Shortcut for an action id, or None."""
    return _BY_ACTION.get(action)


def accel_for(action):
    """Return the primary accel string for an action, or None if it has none."""
    s = _BY_ACTION.get(action)
    if s is None or not s.accels:
        return None
    return s.accels[0]


def accels_for(action):
    """Return the full tuple of accel strings for an action (possibly empty)."""
    s = _BY_ACTION.get(action)
    return s.accels if s is not None else ()


def shortcuts_for(scope):
    """
    Return the shortcuts applicable to a toolkit scope: entries marked
    SCOPE_BOTH plus those marked for that specific toolkit. `scope` is
    SCOPE_GTK3 or SCOPE_GTK4.
    """
    return tuple(s for s in SHORTCUTS
                 if s.scope == SCOPE_BOTH or s.scope == scope)


def grouped_shortcuts(scope):
    """
    Return the applicable shortcuts for a scope grouped by their `group`
    heading, as an ordered list of (group_name, [Shortcut, ...]). Group order
    follows first appearance in SHORTCUTS. Entries with no accelerators (e.g.
    About) are omitted, since a shortcuts window only lists key bindings.
    """
    order = []
    buckets = {}
    for s in shortcuts_for(scope):
        if not s.accels:
            continue
        if s.group not in buckets:
            buckets[s.group] = []
            order.append(s.group)
        buckets[s.group].append(s)
    return [(g, buckets[g]) for g in order]


# --------------------------------------------------------------------------- #
# Content layout: the editor / preview text column and fenced-code boxes.
#
# Both front-ends draw the same thing with their own toolkit (gtk3_textview /
# gtk4_textview); the numbers and geometry live here so the two stay identical
# and the arithmetic is unit-testable without a display.
# --------------------------------------------------------------------------- #

# Side margin (px) between the view edge and the text when the column is not
# being narrowed by the maximum-content-width preference.
CONTENT_BASE_MARGIN = 8

# Fenced-code boxes. The box spans the text column; the code inside is inset
# horizontally by CODE_BOX_INSET. Vertically, the first and last lines of a
# block get CODE_BOX_GAP + CODE_BOX_PAD extra pixels: GAP stays outside the
# box (space from the neighbouring paragraph), PAD inside it.
CODE_BOX_INSET = 12
CODE_BOX_GAP = 4
CODE_BOX_PAD = 6
CODE_BOX_RADIUS = 6
# The box is tinted from the view's own text colour, so it suits light and dark
# styles alike: a faint fill and a slightly stronger 1 px border.
CODE_BOX_FILL_ALPHA = 0.05
CODE_BOX_BORDER_ALPHA = 0.18
# Used instead of a drawn box where the toolkit cannot draw one (GTK 3 without
# PyGObject's cairo support): a plain full-width band behind the block.
CODE_BOX_FALLBACK_BACKGROUND = "#f2f2f2"


def content_margin(view_width, max_width, base=CONTENT_BASE_MARGIN):
    """
    Side margin (px, applied on both sides) that centres the text column in a
    view `view_width` pixels wide so the column is at most `max_width` pixels.
    `max_width` of None (or <= 0) means no limit, which gives `base`. The margin
    never drops below `base`.
    """
    if not max_width or max_width <= 0 or view_width <= 0:
        return base
    return max(base, (int(view_width) - int(max_width)) // 2)


def code_box_rect(view_width, margin, top_y, bottom_y, bottom_h, below_lines=0):
    """
    Geometry of one fenced-code box, in buffer coordinates, as (x, y, w, h).

    `margin` is the view's current side margin, `top_y` the y of the block's
    first line, and `bottom_y` / `bottom_h` the y and height of its last line,
    as reported by the toolkit's get_line_yrange(). A line's height includes
    the pixels above/below it, so the block's extra GAP is trimmed off both
    ends, and the view's own line spacing (`below_lines`, added under every
    line) is trimmed from the bottom so the box ends just under the last line.
    """
    x = margin
    w = max(0, view_width - 2 * margin)
    y = top_y + CODE_BOX_GAP
    bottom = bottom_y + bottom_h - CODE_BOX_GAP - max(0, int(below_lines))
    return (x, y, w, max(0, bottom - y))
