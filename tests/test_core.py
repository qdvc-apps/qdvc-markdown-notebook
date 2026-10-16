"""Unit tests for the GTK-free core (no display needed).

    python3 -m unittest discover -s tests -t .

Covers the pieces behind the fenced-code boxes, the maximum content width, and
the icon / launcher identity; scripts/build-app.sh runs these before installing.
"""

import os
import tempfile
import unittest
from unittest import mock

from qdvc import highlight_rules, pango_markdown, settings, ui_prefs
from qdvc.config import APP_ID, BUNDLED_ICON_NAME, STOCK_ICON_NAME

NOTE = "\n".join([
    "# Title",               # 0
    "Some text.",            # 1
    "```python",             # 2
    "def f(x):",             # 3
    "",                      # 4
    "    return x < 2",      # 5
    "```",                   # 6
    "After.",                # 7
    "```",                   # 8
    "unterminated",          # 9
])


class FenceBlocksTest(unittest.TestCase):
    def test_blocks_span_fence_to_fence(self):
        self.assertEqual(highlight_rules.fence_blocks(NOTE), [(2, 6), (8, 9)])

    def test_no_fences(self):
        self.assertEqual(highlight_rules.fence_blocks("a\nb"), [])

    def test_indented_fence_and_adjacent_blocks(self):
        text = "  ```\nx\n  ```\n```\ny\n```"
        self.assertEqual(highlight_rules.fence_blocks(text), [(0, 2), (3, 5)])

    def test_code_block_tag_has_no_character_background(self):
        # The box replaces the per-character shading of fenced code.
        self.assertNotIn("background", highlight_rules.TAG_SPECS["code_block"])
        self.assertIn("background", highlight_rules.TAG_SPECS["code_inline"])

    def test_spans_cover_whole_block_lines(self):
        spans = [s for s in highlight_rules.iter_spans(NOTE) if s[0] == "code_block"]
        lines = NOTE.split("\n")
        starts = {sum(len(l) + 1 for l in lines[:i]) for i in range(2, 7)}
        self.assertTrue(starts <= {s[1] for s in spans})


class PreviewBlocksTest(unittest.TestCase):
    def test_render_is_join_of_blocks(self):
        for font in (None, "Mono 10"):
            blocks = pango_markdown.render_blocks(NOTE, font)
            self.assertEqual(pango_markdown.render(NOTE, font),
                             "\n".join(m for _k, m in blocks))

    def test_code_blocks_are_separate_and_unshaded(self):
        blocks = pango_markdown.render_blocks(NOTE)
        kinds = [k for k, _m in blocks]
        self.assertEqual(kinds, ["text", "code", "text", "code"])
        code = blocks[1][1]
        self.assertIn("&lt;", code)                 # escaped
        self.assertNotIn("background", code)        # boxed, not shaded
        self.assertEqual(code.count("\n"), 2)       # three body lines

    def test_inline_code_keeps_its_shading(self):
        (kind, markup), = pango_markdown.render_blocks("use `x` here")
        self.assertEqual(kind, pango_markdown.BLOCK_TEXT)
        self.assertIn("background", markup)

    def test_empty_fence_produces_no_code_block(self):
        kinds = [k for k, _m in pango_markdown.render_blocks("a\n```\n```\nb")]
        self.assertNotIn(pango_markdown.BLOCK_CODE, kinds)


class LayoutTest(unittest.TestCase):
    def test_content_margin(self):
        base = ui_prefs.CONTENT_BASE_MARGIN
        self.assertEqual(ui_prefs.content_margin(1600, None), base)
        self.assertEqual(ui_prefs.content_margin(1600, 0), base)
        self.assertEqual(ui_prefs.content_margin(1600, 1000), 300)
        self.assertEqual(ui_prefs.content_margin(1001, 1000), base)
        self.assertEqual(ui_prefs.content_margin(500, 1000), base)

    def test_code_box_rect(self):
        gap, pad = ui_prefs.CODE_BOX_GAP, ui_prefs.CODE_BOX_PAD
        # First line at y=100 (its height includes gap+pad above), last line at
        # y=160, 20 px of text + 3 px line spacing + gap + pad below.
        last_h = 20 + 3 + gap + pad
        x, y, w, h = ui_prefs.code_box_rect(800, 50, 100, 160, last_h, 3)
        self.assertEqual((x, w), (50, 700))
        self.assertEqual(y, 100 + gap)
        self.assertEqual(y + h, 160 + 20 + pad)


class ContentWidthSettingsTest(unittest.TestCase):
    def test_defaults(self):
        s = settings.Settings()
        self.assertTrue(s.limit_content_width)
        self.assertEqual(s.max_content_width, 1000)
        self.assertEqual(s.content_max_width(), 1000)

    def test_off_means_unlimited(self):
        s = settings.Settings()
        s.set_limit_content_width(False)
        self.assertIsNone(s.content_max_width())

    def test_clamp_validate_and_reset(self):
        s = settings.Settings()
        s.set_max_content_width(10)
        self.assertEqual(s.max_content_width, settings.MIN_MAX_CONTENT_WIDTH)
        s.set_max_content_width(10 ** 6)
        self.assertEqual(s.max_content_width, settings.MAX_MAX_CONTENT_WIDTH)
        s._apply({"limit_content_width": "yes", "max_content_width": True})
        self.assertTrue(s.limit_content_width)          # invalid: unchanged
        self.assertEqual(s.max_content_width, settings.MAX_MAX_CONTENT_WIDTH)
        s.set_limit_content_width(False)
        s.reset_content_width()
        self.assertEqual((s.limit_content_width, s.max_content_width), (True, 1000))

    def test_round_trip_dict(self):
        s = settings.Settings()
        s.set_limit_content_width(False)
        s.set_max_content_width(1234)
        t = settings.Settings()
        t._apply(s.to_dict())
        self.assertEqual((t.limit_content_width, t.max_content_width), (False, 1234))
        self.assertNotIn("max_content_width", t._extra)


class IdentityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.join(self.tmp.name, "data")
        env = {"XDG_DATA_HOME": self.home,
               "XDG_DATA_DIRS": os.path.join(self.tmp.name, "system")}
        self.env = mock.patch.dict(os.environ, env)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_bundled_icons_ship_with_the_app(self):
        folder = settings.bundled_icons_dir()
        self.assertIsNotNone(folder)
        for sub, name in (("scalable", f"{BUNDLED_ICON_NAME}.svg"),
                          ("symbolic", f"{BUNDLED_ICON_NAME}-symbolic.svg")):
            self.assertTrue(os.path.isfile(
                os.path.join(folder, "hicolor", sub, "apps", name)))

    def test_default_icon_name_follows_installation(self):
        self.assertEqual(settings.default_icon_name(), STOCK_ICON_NAME)
        apps = os.path.join(self.home, "icons", "hicolor", "scalable", "apps")
        os.makedirs(apps)
        open(os.path.join(apps, f"{BUNDLED_ICON_NAME}.svg"), "w").close()
        self.assertEqual(settings.default_icon_name(), BUNDLED_ICON_NAME)

    def test_launcher_is_named_after_the_app_id(self):
        self.assertEqual(os.path.basename(settings.desktop_file_path()),
                         f"{APP_ID}.desktop")

    def test_legacy_launcher_is_renamed_not_duplicated(self):
        legacy = settings.legacy_desktop_file_path()
        os.makedirs(os.path.dirname(legacy))
        with open(legacy, "w") as fh:
            fh.write("[Desktop Entry]\nExec=/my/own/exec %F\nIcon=old\n")
        self.assertTrue(settings.update_desktop_icon("new-icon"))
        self.assertFalse(os.path.exists(legacy))
        with open(settings.desktop_file_path()) as fh:
            text = fh.read()
        self.assertIn("Exec=/my/own/exec %F", text)
        self.assertIn("Icon=new-icon", text)

    def test_desktop_template_matches_identity(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "data", f"{APP_ID}.desktop.in")) as fh:
            text = fh.read()
        self.assertIn(f"Icon={BUNDLED_ICON_NAME}\n", text)
        self.assertIn("StartupWMClass=qdvc-markdown-notebook\n", text)
        self.assertIn("Exec=@BINDIR@/qdvc-markdown-notebook %F\n", text)


if __name__ == "__main__":
    unittest.main()
