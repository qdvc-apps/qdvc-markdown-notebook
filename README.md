# QDVC Markdown Notebook

A **quick and dirty, vibe-coded** (QDVC) three-pane markdown notebook for the Linux desktop, in the spirit
of FSNotes, Notational Velocity, and QOwnNotes — built with **GTK 3 / PyGObject**
for a native MATE / GNOME2-era look and feel (think Pluma and Atril), plus a
parallel **GTK 4 / libadwaita** front-end for a modern GNOME look.

It points at a folder of `.md` files and gives you:

- **Left pane** — a tree: *All Notes*, *Empty Notes*, and *Subfolders* (with each
  immediate subfolder listed underneath).
- **Middle pane** — a search box plus the list of notes for the selected sidebar item.
- **Right pane** — a monospace editor with lightweight markdown syntax highlighting (no font-size variation).
  Fenced code blocks sit in a box, in the editor and in the rendered preview, and
  on a wide window the text stays in a centred column (1000 px by default; set or
  turn off in Preferences).

Plus a menu bar, toolbar (New / Save / Refresh / Slugify / Card view / Read-only / Preview / Outline), and a status bar.

- Vibe-coding details in [vibe-coding/](vibe-coding/)
- See [docs/MAINTENANCE.md](docs/MAINTENANCE.md) for architecture and maintainer notes.

## Usage

```bash
python3 qdvc_markdown_notebook.py /path/to/markdown/data   # open a folder
python3 qdvc_markdown_notebook.py                          # start empty, Ctrl+O to open
python3 qdvc_markdown_notebook.py --gtk4 [folder]          # use the GTK 4 front-end
python3 qdvc_markdown_notebook.py --gtk3 [folder]          # use the GTK 3 front-end (default)
```

The front-end is chosen by (1) a `--gtk3` / `--gtk4` flag, else (2) the
`ui_backend` setting saved in the config, else (3) the default, GTK 3. The
GTK 4 front-end also exposes the toolkit selector in its Preferences (takes
effect on next launch). If GTK 4 / libadwaita isn't installed, the app prints a
note and falls back to GTK 3.

## Requirements

- Python 3.10+
- PyGObject with **one** of:
  - GTK 3 (`python3-gi`, `gir1.2-gtk-3.0`, and `python3-gi-cairo` to draw the
    boxes around fenced code) — the default front-end; or
  - GTK 4 + libadwaita (`gir1.2-gtk-4.0`, `gir1.2-adw-1`) — the modern front-end
- PyYAML — for saving settings; the app runs without it (nothing persists)

On Debian/Ubuntu/MATE:

```bash
# GTK 3 (default):
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 python3-yaml
# GTK 4 / libadwaita (optional, for --gtk4):
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 python3-yaml
```

## Install (application menu entry, Dock)

From the repository root:

```bash
scripts/build-app.sh --install   # check, test and install for your user
```

That installs the app under `~/.local` (no root needed): it appears in
Activities / the application menu with its own icon and can be pinned to the
Dock, and `qdvc-markdown-notebook` runs it from a terminal (if `~/.local/bin` is
on your `PATH`). After pulling or editing the code, run the same command again:
if the app is running it is asked to quit (it prompts about unsaved changes)
and started again.

```bash
scripts/build-app.sh             # check dependencies, run the tests, stage build/
scripts/build-app.sh --no-tests  # skip the tests
scripts/build-app.sh --run       # start the staged (or, with --install, installed) app
scripts/build-app.sh --uninstall # remove it again (your notes and settings are untouched)
python3 -m unittest discover -s tests -t .   # the tests on their own
```

What `--install` puts where (set `PREFIX` to use another prefix than `~/.local`):

| Path | What |
| --- | --- |
| `~/.local/share/qdvc-markdown-notebook/app/` | the program |
| `~/.local/bin/qdvc-markdown-notebook` | the launcher |
| `~/.local/share/applications/qdvc.MarkdownNotebook.desktop` | the menu entry, named after the application ID so GNOME on Wayland matches the window to it |
| `~/.local/share/icons/hicolor/{scalable,symbolic}/apps/qdvc.MarkdownNotebook*.svg` | the icons |

An older hand-made `~/.local/share/applications/qdvc-markdown-notebook.desktop`
(the name earlier versions of this README suggested) is removed by `--install`,
since the new entry replaces it; if you run the app without installing it, the
app renames such a file to `qdvc.MarkdownNotebook.desktop` itself.

To write the launcher by hand instead, start from
`data/qdvc.MarkdownNotebook.desktop.in` and replace `@BINDIR@/qdvc-markdown-notebook`
with `python3 /full/path/to/qdvc_markdown_notebook.py` (the script must sit next
to its `qdvc/` package and `data/` folder). Save it as
`~/.local/share/applications/qdvc.MarkdownNotebook.desktop`, check it with
`desktop-file-validate`, and refresh the menu with `update-desktop-database
~/.local/share/applications`. Notes:

- `%F` lets the launcher pass a folder you drop onto the icon as the working
  folder argument; launching with no argument starts empty (use Ctrl+O).
- `Icon=qdvc.MarkdownNotebook` is the app's own icon (`data/icons/`, regenerated
  by `tools/make_icon.py`). It resolves once the icons are installed in your icon
  theme (`--install` does that); otherwise use `Icon=accessories-text-editor`,
  the stock freedesktop text-editor icon, which is also what the app falls back
  to for its window when it can't find its own. Running from a checkout, the
  window still shows the app's icon, from `data/icons`.
- A **custom icon set** can be chosen in *Edit → Preferences → Interface*: point
  it at a folder containing `16x16.png`, `22x22.png`, `24x24.png`, `32x32.png`,
  `48x48.png`, `256x256.png`, and `scalable.svg`. The app uses those for its own
  window/taskbar icon immediately, **and** installs them into your user icon
  theme (`~/.local/share/icons/hicolor/…`) under the name
  `qdvc-markdown-notebook`, rewriting the `Icon=` line of its per-user `.desktop`
  file to match — so panels and application menus pick the icon up too. Clearing
  the setting reverts to the default icon (and removes the installed copies).
- `StartupWMClass=qdvc-markdown-notebook` lets an X11 panel/taskbar match the
  running window to this entry (the app sets its program name to match); on
  Wayland, GNOME matches by the application ID, `qdvc.MarkdownNotebook`, which is
  why the file carries that name.

For a system-wide entry available to all users, place the file in
`/usr/share/applications/` instead (requires root).
