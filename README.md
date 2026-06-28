# QDVC Markdown Notebook

A lightweight three-pane markdown notebook for the Linux desktop, in the spirit
of FSNotes, Notational Velocity, and QOwnNotes — built with **GTK 3 / PyGObject**
for a native MATE / GNOME2-era look and feel (think Pluma and Atril).

It points at a folder of `.md` files and gives you:

- **Left pane** — "All Notes" plus the immediate subfolders of your data folder.
- **Middle pane** — the list of notes in the selected folder.
- **Right pane** — a monospace editor with lightweight markdown syntax highlighting (no font-size variation).

Plus a menu bar, toolbar (New / Save), and a status bar.

## Usage

```bash
python3 qdvc_markdown_notebook.py /path/to/markdown/data   # open a folder
python3 qdvc_markdown_notebook.py                          # start empty, Ctrl+O to open
```

## Requirements

- Python 3
- GTK 3 with PyGObject (`python3-gi`, `gir1.2-gtk-3.0`)
- PyYAML (optional) — for saving settings; the app runs without it

On Debian/Ubuntu/MATE:

```bash
sudo apt install python3-gi gir1.2-gtk-3.0 python3-yaml
```

## Settings

Persistent settings live in a plain, git-trackable YAML file at
`~/.config/qdvcmdnb/config.yml` (or under `$XDG_CONFIG_HOME`). It remembers:

- **Editor font** — set via *View → Set Editor Font…*
- **Recent working folders** — reopen them from *File → Open Recent*

## Tabs

Open notes across multiple tabs:

- **Single-click** a note — opens it in the current tab (replacing its content).
- **Right-click** a note → *Open in new tab*.
- **Ctrl+T** — new empty tab. **Ctrl+W** — close the current tab (also the little
  × on each tab).
- With only one tab open, the tab bar is hidden.

## Keyboard shortcuts

| Action               | Shortcut |
| -------------------- | -------- |
| New note             | Ctrl+N   |
| Save note            | Ctrl+S   |
| Open working folder  | Ctrl+O   |
| New tab              | Ctrl+T   |
| Close tab            | Ctrl+W   |
| Quit                 | Ctrl+Q   |

See [MAINTENANCE.md](MAINTENANCE.md) for architecture and maintainer notes.
