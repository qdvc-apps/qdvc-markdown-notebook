#!/usr/bin/env python3
"""Generate the app icons in the GNOME (Adwaita) style.

    python3 tools/make_icon.py            # writes data/icons/hicolor/...
    python3 tools/make_icon.py --preview  # also build/icon-preview.png (needs rsvg-convert)

The design follows the family's GNOME icons (qdvc-progress-gtk4's spreadsheet
card, qdvc-gtd-eml-gtk4's sealed envelope): one object on the 128 × 128 app
icon grid, lit from above, with a soft darker bottom edge (the HIG's
"thickness" cue), on the Adwaita palette. Here the object is a ring-bound
notebook: a white page with a purple spine and binding rings, a heading (a
purple "#" and a bar), a couple of text lines, a fenced code block drawn as a
box, and a purple badge carrying the Markdown mark (M and a down arrow). The
symbolic variant is a page outline with the Markdown mark, as filled shapes
only, so GTK can recolour it.

Writes:
  data/icons/hicolor/scalable/apps/qdvc.MarkdownNotebook.svg
  data/icons/hicolor/symbolic/apps/qdvc.MarkdownNotebook-symbolic.svg
"""

import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ID = "qdvc.MarkdownNotebook"

# Adwaita palette.
PURPLE_1, PURPLE_3, PURPLE_4, PURPLE_5 = "#dc8add", "#9141ac", "#813d9c", "#613583"
LIGHT_3, LIGHT_4, LIGHT_5 = "#deddda", "#c0bfbc", "#9a9996"
DARK_2 = "#5e5c64"
GREEN_4, BLUE_3 = "#2ec27e", "#3584e4"


def app_icon() -> str:
    x0, y0, w, h, r = 20, 12, 92, 100, 10      # the page
    spine = 16                                  # spine width
    out = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" '
        'viewBox="0 0 128 128">',
        "<defs>",
        '<linearGradient id="edge" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{LIGHT_4}"/><stop offset="1" stop-color="{LIGHT_5}"/>'
        "</linearGradient>",
        '<linearGradient id="page" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#f6f5f4"/>'
        "</linearGradient>",
        '<linearGradient id="spine" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="{PURPLE_4}"/><stop offset="1" stop-color="{PURPLE_3}"/>'
        "</linearGradient>",
        '<linearGradient id="badge" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="#a65fc4"/><stop offset="1" stop-color="{PURPLE_4}"/>'
        "</linearGradient>",
        f'<clipPath id="spine-clip"><rect width="{x0 + spine}" height="128"/></clipPath>',
        "</defs>",
        # The notebook's bottom edge (purple under the spine), then the page.
        f'<rect x="{x0}" y="{y0 + 6}" width="{w}" height="{h}" rx="{r}" fill="url(#edge)"/>',
        f'<rect x="{x0}" y="{y0 + 6}" width="{w}" height="{h}" rx="{r}" fill="{PURPLE_5}" '
        'clip-path="url(#spine-clip)"/>',
        f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" rx="{r}" fill="url(#page)"/>',
        # The spine: the page's left strip, square on its inner side.
        f'<path d="M{x0 + r} {y0} h{spine - r} v{h} h-{spine - r} '
        f'a{r} {r} 0 0 1 -{r} -{r} v-{h - 2 * r} a{r} {r} 0 0 1 {r} -{r} z" '
        'fill="url(#spine)"/>',
    ]
    # Binding rings across the spine edge.
    for i in range(5):
        cy = y0 + 16 + i * 17
        out.append(f'<rect x="{x0 + spine - 6}" y="{cy - 3}" width="12" height="6" '
                   f'rx="3" fill="{DARK_2}"/>')
        out.append(f'<rect x="{x0 + spine - 5}" y="{cy - 2.5}" width="10" height="2.5" '
                   'rx="1.25" fill="#ffffff" fill-opacity="0.35"/>')
    # Heading: a purple "#" and a dark bar.
    hx, hy = x0 + spine + 10, y0 + 12
    out.append(
        f'<path d="M{hx + 3} {hy} l-2 14 M{hx + 9} {hy} l-2 14 '
        f'M{hx - 0.5} {hy + 4.5} h12 M{hx - 1.5} {hy + 9.5} h12" fill="none" '
        f'stroke="{PURPLE_3}" stroke-width="2.6" stroke-linecap="round"/>')
    out.append(f'<rect x="{hx + 17}" y="{hy + 4}" width="34" height="6" rx="3" '
               f'fill="{DARK_2}"/>')
    # Text lines.
    tx = x0 + spine + 10
    for i, length in enumerate((56, 48, 52)):
        out.append(f'<rect x="{tx}" y="{hy + 22 + i * 9}" width="{length}" height="4" '
                   f'rx="2" fill="{LIGHT_4}"/>')
    # A fenced code block, drawn as a box (as the app now draws them).
    cx, cy, cw, ch = tx - 3, hy + 50, 62, 30
    out.append(f'<rect x="{cx + 0.5}" y="{cy + 0.5}" width="{cw - 1}" height="{ch - 1}" '
               f'rx="5" fill="#f2f1f0" stroke="{LIGHT_3}" stroke-width="1.5"/>')
    for i, (indent, length, colour) in enumerate(((0, 22, GREEN_4), (8, 28, BLUE_3),
                                                  (8, 14, GREEN_4))):
        out.append(f'<rect x="{cx + 7 + indent}" y="{cy + 6 + i * 7}" width="{length}" '
                   f'height="4" rx="2" fill="{colour}"/>')
    # Badge with the Markdown mark.
    bx, by, br = 94, 92, 21
    out += [
        f'<circle cx="{bx}" cy="{by + 3}" r="{br}" fill="{PURPLE_5}"/>',
        f'<circle cx="{bx}" cy="{by}" r="{br}" fill="url(#badge)"/>',
        f'<circle cx="{bx}" cy="{by}" r="{br - 1}" fill="none" stroke="{PURPLE_1}" '
        'stroke-opacity="0.35" stroke-width="1"/>',
        # M
        f'<path d="M{bx - 13} {by + 7} v-14 l6 7 l6 -7 v14" fill="none" '
        'stroke="#ffffff" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>',
        # Down arrow
        f'<path d="M{bx + 8} {by - 7} v9" fill="none" stroke="#ffffff" stroke-width="4" '
        'stroke-linecap="round"/>',
        f'<path d="M{bx + 2.5} {by + 1} h11 l-5.5 7 z" fill="#ffffff" stroke="#ffffff" '
        'stroke-width="1.5" stroke-linejoin="round"/>',
        "</svg>",
    ]
    return "\n".join(out) + "\n"


def symbolic_icon() -> str:
    """16 × 16, filled shapes only (GNOME recolours symbolic icons)."""
    return """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
<path fill="#2e3436" fill-rule="evenodd" d="M2.5 2h11A1.5 1.5 0 0 1 15 3.5v9a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 1 12.5v-9A1.5 1.5 0 0 1 2.5 2zm0 1.5v9h11v-9z"/>
<path fill="#2e3436" d="M3.5 11V5H5l1.25 1.75L7.5 5H9v6H7.5V7.6L6.25 9.2 5 7.6V11z"/>
<path fill="#2e3436" d="M10.5 5h1.5v3.25h1.25L11.25 11 9.25 8.25h1.25z"/>
</svg>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true")
    args = ap.parse_args()
    base = os.path.join(ROOT, "data", "icons", "hicolor")
    paths = {
        os.path.join(base, "scalable", "apps", f"{APP_ID}.svg"): app_icon(),
        os.path.join(base, "symbolic", "apps", f"{APP_ID}-symbolic.svg"): symbolic_icon(),
    }
    for path, svg in paths.items():
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(svg)
        print("wrote", os.path.relpath(path, ROOT))
    if args.preview:
        os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
        out = os.path.join(ROOT, "build", "icon-preview.png")
        try:
            subprocess.run(["rsvg-convert", "-w", "256", "-h", "256", "-o", out,
                            list(paths)[0]], check=True)
            print("wrote", os.path.relpath(out, ROOT))
        except (OSError, subprocess.CalledProcessError) as e:
            print("preview needs rsvg-convert:", e, file=sys.stderr)


if __name__ == "__main__":
    main()
