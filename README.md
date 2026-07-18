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
  - GTK 3 (`python3-gi`, `gir1.2-gtk-3.0`) — the default front-end; or
  - GTK 4 + libadwaita (`gir1.2-gtk-4.0`, `gir1.2-adw-1`) — the modern front-end
- PyYAML — for saving settings; the app runs without it (nothing persists)

On Debian/Ubuntu/MATE:

```bash
# GTK 3 (default):
sudo apt install python3-gi gir1.2-gtk-3.0 python3-yaml
# GTK 4 / libadwaita (optional, for --gtk4):
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 python3-yaml
```

## Desktop integration (application menu entry)

To make "QDVC Markdown Notebook" appear in your MATE/GNOME application menu,
install a `.desktop` file.

First decide where the script lives. Assuming you keep the project at
`~/Applications/qdvc-markdown-notebook/` (adjust the `Exec` path below to match),
create `~/.local/share/applications/qdvc-markdown-notebook.desktop` with:

```ini
[Desktop Entry]
Type=Application
Name=QDVC Markdown Notebook
Comment=Three-pane markdown notebook viewer/editor
Exec=python3 /home/YOUR_USERNAME/Applications/qdvc-markdown-notebook/qdvc_markdown_notebook.py %F
Icon=accessories-text-editor
Terminal=false
Categories=Office;Utility;TextEditor;
MimeType=text/markdown;
StartupNotify=true
StartupWMClass=qdvc-markdown-notebook
```

Notes:
- Replace the `Exec` path with the absolute path to `qdvc_markdown_notebook.py`.
  The script must be able to find its `qdvc/` package alongside it, which
  it will as long as you point `Exec` at the script in its own directory.
- `%F` lets the launcher pass a folder you drop onto the icon as the working
  folder argument; launching with no argument starts empty (use Ctrl+O).
- `Icon=accessories-text-editor` is a standard freedesktop icon present on a
  typical GNOME/MATE install (it's the generic text-editor icon, the same family
  Pluma uses). To use your own icon instead, point `Icon=` at an absolute path to
  a `.png` or `.svg`. Alternatively, set a **custom icon set** in *Edit →
  Preferences → Interface*: point it at a folder containing `16x16.png`,
  `22x22.png`, `24x24.png`, `32x32.png`, `48x48.png`, `256x256.png`, and
  `scalable.svg`. The app uses those for its own window/taskbar icon immediately,
  **and** installs them into your user icon theme
  (`~/.local/share/icons/hicolor/…`) under the name `qdvc-markdown-notebook`,
  rewriting the `Icon=` line of its per-user `.desktop` file to match — so panels
  and application menus pick the icon up too. Clearing the setting reverts to the
  stock icon (and removes the installed copies). If you set a custom icon set you
  can leave `Icon=accessories-text-editor` as-is; the app will update it.
- `StartupWMClass=qdvc-markdown-notebook` lets the panel/taskbar match the running
  window to this entry, so it shows the app icon instead of a generic window icon.
  The app sets its program name to `qdvc-markdown-notebook` to match; the app also
  sets its window icon to `accessories-text-editor` directly, so the icon appears
  even before any `.desktop` matching.

Then refresh the menu database (often automatic):

```bash
update-desktop-database ~/.local/share/applications
```

For a system-wide entry available to all users, place the file in
`/usr/share/applications/` instead (requires root).
