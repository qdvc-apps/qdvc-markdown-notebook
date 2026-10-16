"""
gtk4_textview.py — the Gtk.TextView behind the GTK 4 editor and preview.

``ContentTextView`` is a plain Gtk.TextView plus two layout features, shared by
the editor and the rendered preview of every tab (the GTK 3 twin is
qdvc/gtk3/gtk3_textview.py; the numbers and geometry both use live in the pure
``qdvc.ui_prefs``):

  * **Maximum content width.** When a limit is set (Preferences), the side
    margins grow so the text column is at most that wide and stays centred,
    like a GNOME document view. Recomputed on every size allocation.
  * **Boxes around fenced code.** The owner passes the line ranges of the
    fenced blocks (``set_code_blocks``); the view tags those lines with extra
    margins/padding and draws one rounded box behind each block in the
    BELOW_TEXT layer, tinted from the view's text colour so it works in light
    and dark styles. (A tag ``background`` only shades the characters
    themselves, which is what this replaces.)

Drawing uses GtkSnapshot / GSK nodes, so no cairo bindings are needed.
"""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, Gsk, Graphene  # noqa: E402

from .. import ui_prefs as L

# Tag names (one ContentTextView per buffer, so fixed names are safe).
TAG_BOX = "qdvc_code_box"           # every line of a block: inset margins
TAG_BOX_FIRST = "qdvc_code_box_first"  # first line: room above, inside the box
TAG_BOX_LAST = "qdvc_code_box_last"    # last line: room below, inside the box

TOP_BOTTOM_MARGIN = 8


class ContentTextView(Gtk.TextView):
    """A TextView with a centred maximum-width column and code-block boxes."""

    __gtype_name__ = "QdvcContentTextView"

    def __init__(self, buffer):
        super().__init__(buffer=buffer)
        self._max_width = None      # px, or None for no limit
        self._margin = L.CONTENT_BASE_MARGIN
        self._line_spacing = 0      # px below each line (and between wraps)
        self._blocks = []           # [(first_line, last_line), ...]
        self.set_left_margin(self._margin)
        self.set_right_margin(self._margin)
        self.set_top_margin(TOP_BOTTOM_MARGIN)
        self.set_bottom_margin(TOP_BOTTOM_MARGIN)
        pad = L.CODE_BOX_GAP + L.CODE_BOX_PAD
        self._tag_box = buffer.create_tag(TAG_BOX)
        self._tag_first = buffer.create_tag(TAG_BOX_FIRST,
                                            pixels_above_lines=pad)
        self._tag_last = buffer.create_tag(TAG_BOX_LAST,
                                           pixels_below_lines=pad)
        self._sync_box_tags()

    # ------------------------------------------------------------ API -- #
    def set_max_content_width(self, width):
        """Limit the text column to `width` px (None or 0: no limit)."""
        self._max_width = int(width) if width else None
        self._update_margins(self.get_width())

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
            e = self._line_start(last + 1)
            if s is None:
                continue
            if e is None:
                e = buf.get_end_iter()
            buf.apply_tag(self._tag_box, s, e)
            buf.apply_tag(self._tag_first, s, self._line_end(first, e))
            ls = self._line_start(last) or s
            buf.apply_tag(self._tag_last, ls, e)
        self.queue_draw()

    # ------------------------------------------------------- layout -- #
    def do_size_allocate(self, width, height, baseline):
        Gtk.TextView.do_size_allocate(self, width, height, baseline)
        self._update_margins(width)

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
    def do_snapshot_layer(self, layer, snapshot):
        if layer != Gtk.TextViewLayer.BELOW_TEXT or not self._blocks:
            return
        fill, border = self._box_colours()
        visible = self.get_visible_rect()
        width = self.get_width()
        for first, last in self._blocks:
            top_it = self._line_start(first)
            bottom_it = self._line_start(last)
            if top_it is None or bottom_it is None:
                continue
            top_y, _h = self.get_line_yrange(top_it)
            bottom_y, bottom_h = self.get_line_yrange(bottom_it)
            x, y, w, h = L.code_box_rect(width, self._margin, top_y,
                                         bottom_y, bottom_h, self._line_spacing)
            if w <= 0 or h <= 0:
                continue
            if y > visible.y + visible.height or y + h < visible.y:
                continue
            rect = Graphene.Rect().init(x, y, w, h)
            rounded = Gsk.RoundedRect()
            rounded.init_from_rect(rect, L.CODE_BOX_RADIUS)
            snapshot.push_rounded_clip(rounded)
            snapshot.append_color(fill, rect)
            snapshot.pop()
            snapshot.append_border(rounded, [1, 1, 1, 1], [border] * 4)

    def _box_colours(self):
        """Fill and border colours, tinted from the current text colour."""
        try:
            fg = self.get_color()                      # GTK >= 4.10
        except AttributeError:  # pragma: no cover - older GTK 4
            fg = self.get_style_context().get_color()
        fill = Gdk.RGBA()
        fill.red, fill.green, fill.blue = fg.red, fg.green, fg.blue
        fill.alpha = L.CODE_BOX_FILL_ALPHA
        border = fill.copy()
        border.alpha = L.CODE_BOX_BORDER_ALPHA
        return fill, border

    # ------------------------------------------------------ helpers -- #
    def _line_start(self, line):
        """Iter at the start of `line`, or None past the end of the buffer."""
        buf = self.get_buffer()
        if line < 0 or line >= buf.get_line_count():
            return None
        found = buf.get_iter_at_line(line)
        if isinstance(found, tuple):    # GTK 4 returns (ok, iter)
            ok, it = found
            return it if ok else None
        return found

    def _line_end(self, line, fallback):
        """Iter at the start of the line after `line` (else `fallback`)."""
        it = self._line_start(line + 1)
        return it if it is not None else fallback
