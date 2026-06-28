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
  The script must be able to find its `qdvcmdnb_lib/` package alongside it, which
  it will as long as you point `Exec` at the script in its own directory.
- `%F` lets the launcher pass a folder you drop onto the icon as the working
  folder argument; launching with no argument starts empty (use Ctrl+O).
- `Icon=accessories-text-editor` is a standard freedesktop icon present on a
  typical GNOME/MATE install (it's the generic text-editor icon, the same family
  Pluma uses). To use your own icon instead, point `Icon=` at an absolute path to
  a `.png` or `.svg`.
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


## Preferences

Open *Edit → Preferences* to configure:

- **Editor font** — the font for the whole editor.
- **Code font** — a separate font for inline code and fenced code blocks.
- **Toolbar style** — whether toolbar button text appears below or beside icons.

These are stored in a plain, git-trackable YAML file at
`~/.config/qdvcmdnb/config.yml` (or under `$XDG_CONFIG_HOME`), along with your
list of recent working folders (reopen them from *File → Open Recent*).

## Tabs

Open notes across multiple tabs:

- **Single-click** a note — opens it in the current tab (replacing its content).
- **Right-click** a note for a menu: *Open in new tab*, *Copy full path*, and
  *Show in file browser*.
- **Ctrl+T** — new empty tab. **Ctrl+W** — close the current tab (also the little
  × on each tab).
- **Ctrl+Tab** / **Ctrl+Shift+Tab** cycle forward/backward through tabs;
  **Alt+1**…**Alt+9** jump straight to a tab.
- Tabs are titled with the note name (truncated past 12 characters).
- With only one tab open, the tab bar is hidden.
- A tab with no note shows a placeholder prompting you to select one.

## Slugify

The toolbar's **Slugify** button renames the current note from its title. It is
enabled only when the note's first line is a level-1 heading (`# …`) shorter than
32 characters. Clicking it asks for confirmation, then renames the file to a
lowercase, dash-separated slug — e.g. a note titled `# My awesome new note!`
becomes `my-awesome-new-note.md`.

## Keyboard shortcuts

| Action                | Shortcut          |
| --------------------- | ----------------- |
| New note              | Ctrl+N            |
| Save note             | Ctrl+S            |
| Open working folder   | Ctrl+O            |
| New tab               | Ctrl+T            |
| Close tab             | Ctrl+W            |
| Next / previous tab   | Ctrl+Tab / Ctrl+Shift+Tab |
| Jump to tab 1–9       | Alt+1 … Alt+9     |
| Quit                  | Ctrl+Q            |

There's also *Help → About* for version and project information.

See [MAINTENANCE.md](MAINTENANCE.md) for architecture and maintainer notes.
