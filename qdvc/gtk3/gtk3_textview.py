"""
gtk3_textview.py — the Gtk.TextView behind the GTK 3 editor and preview.

``ContentTextView`` is a plain Gtk.TextView plus two layout features, shared by
the editor and the rendered preview of every tab (the GTK 4 twin is
qdvc/gtk4/gtk4_textview.py; the numbers and geometry both use live in the pure
``qdvc.ui_prefs``):

  * **Maximum content width.** When a limit is set (Preferences), the side
    margins grow so the text column is at most that wide and stays centred.
    Recomputed whenever the view is resized ("size-allocate"); the margins are
    applied from an idle callback, since changing them re-lays-out the view and
    GTK 3 dislikes that in the middle of an allocation.
  * **Boxes around fenced code.** The owner passes the line ranges of the
    fenced blocks (``set_code_blocks``); the view tags those lines with extra
    margins/padding and draws one rounded box behind each block in the
    BELOW_TEXT layer (``do_draw_layer``), tinted from the view's text colour.
    (A tag ``background`` only shades the characters themselves, which is what
    this replaces.)

Drawing needs PyGObject's cairo support (``python3-gi-cairo``). Without it the
view falls back to a plain full-width band behind each block (a tag
``paragraph-background``), so the app still runs on a bare GTK 3 install.
"""

import math

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib  # noqa: E402

from .. import ui_prefs as L

try:  # cairo is optional: see the module docstring
    gi.require_foreign("cairo")
    import cairo  # noqa: F401  (needed for the draw_layer vfunc argument)
    HAVE_CAIRO = True
except Exception:  # ImportError, or a stub gi without require_foreign
    HAVE_CAIRO = False

# Tag names (one ContentTextView per buffer, so fixed names are safe).
TAG_BOX = "qdvc_code_box"           # every line of a block: inset margins
TAG_BOX_FIRST = "qdvc_code_box_first"  # first line: room above, inside the box
TAG_BOX_LAST = "qdvc_code_box_last"    # last line: room below, inside the box

TOP_BOTTOM_MARGIN = 8


class ContentTextView(Gtk.TextView):
    """A TextView with a centred maximum-width column and code-block boxes."""

    __gtype_name__ = "QdvcGtk3ContentTextView"

    def __init__(self, buffer):
        super().__init__(buffer=buffer)
        self._max_width = None      # px, or None for no limit
        self._margin = L.CONTENT_BASE_MARGIN
        self._line_spacing = 0      # px below each line (and between wraps)
        self._blocks = []           # [(first_line, last_line), ...]
        self._margin_idle = 0
        self.set_left_margin(self._margin)
        self.set_right_margin(self._margin)
        self.set_top_margin(TOP_BOTTOM_MARGIN)
        self.set_bottom_margin(TOP_BOTTOM_MARGIN)
        pad = L.CODE_BOX_GAP + L.CODE_BOX_PAD
        if HAVE_CAIRO:
            self._tag_box = buffer.create_tag(TAG_BOX)
        else:
            self._tag_box = buffer.create_tag(
                TAG_BOX, paragraph_background=L.CODE_BOX_FALLBACK_BACKGROUND)
        self._tag_first = buffer.create_tag(TAG_BOX_FIRST,
                                            pixels_above_lines=pad)
        self._tag_last = buffer.create_tag(TAG_BOX_LAST,
                                           pixels_below_lines=pad)
        self._sync_box_tags()
        self.connect("size-allocate", self._on_size_allocate)

    # ------------------------------------------------------------ API -- #
    def set_max_content_width(self, width):
        """Limit the text column to `width` px (None or 0: no limit)."""
        self._max_width = int(width) if width else None
        self._update_margins(self.get_allocated_width())

    def set_line_spacing(self, pixels):
        """Extra pixels below each line and between the rows of a wrapped one."""
        self._line_spacing = max(0, int(pixels))
        self.set_pixels_below_lines(self._line_spacing)
        self.set_pixels_inside_wrap(self._line_spacing)
        self._sync_box_tags()

    def set_code_blocks(self, blocks):
        """Box these (first_line, last_line) ranges (0-based, inclusive)."""
        buf = self.get_buffer()
        start, end = buf.get_bounds()
        for tag in (self._tag_box, self._tag_first, self._tag_last):
            buf.remove_tag(tag, start, end)
        self._blocks = list(blocks)
        for first, last in self._blocks:
            s = self._line_start(first)
            if s is None:
                continue
            e = self._line_start(last + 1) or buf.get_end_iter()
            buf.apply_tag(self._tag_box, s, e)
            buf.apply_tag(self._tag_first, s, self._line_start(first + 1) or e)
            buf.apply_tag(self._tag_last, self._line_start(last) or s, e)
        self.queue_draw()

    # ------------------------------------------------------- layout -- #
    def _on_size_allocate(self, _widget, allocation):
        if L.content_margin(allocation.width, self._max_width) == self._margin:
            return
        if not self._margin_idle:
            self._margin_idle = GLib.idle_add(self._apply_margin_idle)

    def _apply_margin_idle(self):
        self._margin_idle = 0
        self._update_margins(self.get_allocated_width())
        return False

    def _update_margins(self, width):
        margin = L.content_margin(width, self._max_width)
        if margin == self._margin:
            return
        self._margin = margin
        self.set_left_margin(margin)
        self.set_right_margin(margin)
        self._sync_box_tags()

    def _sync_box_tags(self):
        inset = self._margin + L.CODE_BOX_INSET
        self._tag_box.set_property("left-margin", inset)
        self._tag_box.set_property("right-margin", inset)
        # A tag's pixels-below replaces the view's own line spacing for that
        # line, so add the spacing back in.
        self._tag_last.set_property(
            "pixels-below-lines",
            self._line_spacing + L.CODE_BOX_GAP + L.CODE_BOX_PAD)

    # ------------------------------------------------------ drawing -- #
    if HAVE_CAIRO:
        def do_draw_layer(self, layer, cr):
            # BELOW_TEXT is drawn in buffer coordinates, after the background
            # and before the text (GTK >= 3.20).
            if layer != Gtk.TextViewLayer.BELOW_TEXT or not self._blocks:
                return
            fg = self.get_style_context().get_color(self.get_state_flags())
            visible = self.get_visible_rect()
            width = self.get_allocated_width()
            for first, last in self._blocks:
                top_it = self._line_start(first)
                bottom_it = self._line_start(last)
                if top_it is None or bottom_it is None:
                    continue
                top_y, _h = self.get_line_yrange(top_it)
                bottom_y, bottom_h = self.get_line_yrange(bottom_it)
                x, y, w, h = L.code_box_rect(width, self._margin, top_y,
                                             bottom_y, bottom_h,
                                             self._line_spacing)
                if w <= 2 or h <= 2:
                    continue
                if y > visible.y + visible.height or y + h < visible.y:
                    continue
                # Half-pixel inset so the 1 px border lands on whole pixels.
                _rounded_rect(cr, x + 0.5, y + 0.5, w - 1, h - 1,
                              L.CODE_BOX_RADIUS)
                cr.set_source_rgba(fg.red, fg.green, fg.blue,
                                   L.CODE_BOX_FILL_ALPHA)
                cr.fill_preserve()
                cr.set_source_rgba(fg.red, fg.green, fg.blue,
                                   L.CODE_BOX_BORDER_ALPHA)
                cr.set_line_width(1)
                cr.stroke()

    # ------------------------------------------------------ helpers -- #
    def _line_start(self, line):
        """Iter at the start of `line`, or None past the end of the buffer."""
        buf = self.get_buffer()
        if line < 0 or line >= buf.get_line_count():
            return None
        return buf.get_iter_at_line(line)


def _rounded_rect(cr, x, y, w, h, r):
    """Add a rounded-rectangle path to the cairo context."""
    r = min(r, w / 2, h / 2)
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()
