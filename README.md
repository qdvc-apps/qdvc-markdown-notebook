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

On Debian/Ubuntu/MATE:

```bash
sudo apt install python3-gi gir1.2-gtk-3.0
```

## Keyboard shortcuts

| Action               | Shortcut |
| -------------------- | -------- |
| New note             | Ctrl+N   |
| Save note            | Ctrl+S   |
| Open working folder  | Ctrl+O   |
| Quit                 | Ctrl+Q   |

See [MAINTENANCE.md](MAINTENANCE.md) for architecture and maintainer notes.
