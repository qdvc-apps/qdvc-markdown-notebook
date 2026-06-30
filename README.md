# QDVC Markdown Notebook

A lightweight three-pane markdown notebook for the Linux desktop, in the spirit
of FSNotes, Notational Velocity, and QOwnNotes — built with **GTK 3 / PyGObject**
for a native MATE / GNOME2-era look and feel (think Pluma and Atril).

It points at a folder of `.md` files and gives you:

- **Left pane** — a tree: *All Notes*, *Empty Notes*, and *Subfolders* (with each
  immediate subfolder listed underneath).
- **Middle pane** — a search box plus the list of notes for the selected sidebar item.
- **Right pane** — a monospace editor with lightweight markdown syntax highlighting (no font-size variation).

Plus a menu bar, toolbar (New / Save / Refresh / Slugify / Card view / Read-only / Preview / Outline), and a status bar.

## Read-only mode

The app starts in **read-only mode** — you can browse and read notes but not edit
them. The status bar shows the current mode in bold, and the toolbar has a
Read-only toggle (pressed in by default). Release it to enter **edit mode**. The
setting applies across all tabs at once.

## Preview

The toolbar's **Preview** toggle replaces the monospace editor with rendered
markdown (headings, bold/italic, lists, blockquotes, code, links) across all
tabs. The rendering uses Pango markup — no WebKit or external browser. Preview is
always read-only: while it is active the Read-only toggle is disabled, and the
status bar shows *Rendered Markdown preview*. Release Preview to return to the
editor.

## Sidebar

The left sidebar is a tree:

- **All Notes** — every note under the working folder.
- **Inbox** — notes that sit at the **top level** of the working folder (those
  not yet filed into a subfolder).
- **Empty Notes** — notes whose content is empty or only whitespace.
- **Subfolders** — expands to each immediate subfolder; selecting a subfolder
  lists its notes. Selecting the *Subfolders* heading itself shows a placeholder
  in both the note list and the editor.

## Search

A search box sits at the top of the note list. Type a term and press **Enter**
or click **Search** to filter the list to notes that match (case-insensitive) in
either their name or their **full contents**. Searching does not happen on every
keystroke. Matching terms are highlighted in yellow in the document you're
viewing. Clearing the box (or pressing its clear icon) removes the filter and the
highlighting. When a search matches nothing, the status bar shows *No search
results found!* in place of the item count.

## Card view

The toolbar's **Card view** toggle (off by default) changes how the note list
shows each note. Instead of just the title, each entry becomes a small card: the
title in **bold**, then the last-modified date and the first line of body text
(the first non-blank line after the note's heading) in a smaller *italic* font.
A thin separator line is drawn between cards, and each card has a little extra
top and bottom padding. Toggle it off to return to the plain title list.

## Headings outline

The toolbar's **Outline** toggle (and *View → Headings outline*, Ctrl+Shift+O)
opens a fourth pane on the right showing the markdown headings of the note in
view as a tree (nested by heading level). Clicking a heading jumps the editor to
that line. The outline updates as you edit the note or switch tabs. Headings
inside fenced code blocks are ignored.

## Menus

- **File** — New note, Save note, Refresh note, Open workspace, Refresh
  workspace, Close workspace, Open recent workspace, New tab, Close tab, Quit.
- **Edit** — Preferences.
- **View** — show/hide the Toolbar and Statusbar; toggle Read-only, Card view,
  Preview, and the Headings outline; and choose the note sort order.
- **Help** — About.



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


## Preferences

Open *Edit → Preferences* (a tabbed dialog) to configure:

**Fonts tab**
- **Editor font** — the font for the editor view.
- **Code font** — a separate font for inline code and fenced code blocks, used in
  both the editor and the markdown preview.
- **Markdown preview font** — the body font for the rendered preview (everything
  except code).
- **Editor line spacing** — extra pixels between lines in the editor (applies to
  code too).
- **Preview line spacing** — extra pixels between lines in the markdown preview
  (applies to code too).

**Interface tab**
- **Toolbar icon text placement** — whether toolbar button text appears below or
  beside icons.
- **Tab title length** — how many characters of a note's name a tab shows before
  it is truncated with an ellipsis.
- **Remember note sort order between sessions** — persist the chosen sort order
  so it is restored next launch.
- **Reopen last workspace and notes on startup** — automatically reopen the last
  workspace, the notes that were open (one per tab), and the previous sidebar
  (pane 1) and note-list (pane 2) selections, when no folder is passed on the
  command line.
- **Custom application icon set** — choose a folder of icons to use in place of
  the stock app icon (see *Desktop integration* below for the required files).

Changes preview live while the dialog is open; **Save** persists them, **Cancel**
reverts. These are stored in a plain, git-trackable YAML file at
`~/.config/qdvcmdnb/config.yml` (or under `$XDG_CONFIG_HOME`), along with your
list of recent workspaces (reopen them from *File → Open recent workspace*).

## Tabs

Open notes across multiple tabs:

- **Single-click** a note — opens it in the current tab (replacing its content).
- **Right-click** a note for a menu: *Open in new tab*, *Move to subfolder*
  (a submenu of the workspace's subfolders; confirms before moving), *Copy full
  path*, and *Show in file browser*. Several items carry an icon. Right-clicking
  does not change the current selection or open the note.
- **Right-click a tab** for the same menu plus a *Locate in subfolders* item:
  clicking it reveals the note in the sidebar (pane 1) and note list (pane 2).
- In **edit mode**, pressing **Tab** in the editor inserts four spaces.
- **Ctrl+T** — new empty tab. **Ctrl+W** — close the current tab (also the little
  × on each tab).
- **Ctrl+Tab** / **Ctrl+Shift+Tab** cycle forward/backward through tabs;
  **Alt+1**…**Alt+9** jump straight to a tab.
- Tabs are titled with the note name, truncated past a configurable length
  (default 12 characters; set it in *Edit → Preferences → Interface*).
- With only one tab open, the tab bar is hidden.
- A tab with no note shows a placeholder prompting you to select one.

## Refresh note

The toolbar's **Refresh note** button (also *File → Refresh note*, Ctrl+R)
reloads the current note from disk — handy if the file was changed by another
program. If the open tab has unsaved changes, you'll get the same
save/discard/cancel prompt as when closing a tab before the reload happens.

## Refresh workspace

*File → Refresh workspace* (Ctrl+Shift+R) re-scans the working folder and
rebuilds the sidebar (pane 1) and note list (pane 2) from disk, picking up files
added, removed, or renamed by other programs. Your current selection is kept
where possible; open tabs are left untouched.

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
| Refresh note          | Ctrl+R            |
| Open workspace        | Ctrl+O            |
| Refresh workspace     | Ctrl+Shift+R      |
| New tab               | Ctrl+T            |
| Close tab             | Ctrl+W            |
| Next / previous tab   | Ctrl+Tab / Ctrl+Shift+Tab |
| Jump to tab 1–9       | Alt+1 … Alt+9     |
| Toggle Read-only      | Ctrl+E            |
| Toggle Card view      | Ctrl+D            |
| Toggle Preview        | Ctrl+`            |
| Toggle Headings outline | Ctrl+Shift+O    |
| Insert 4 spaces (in editor) | Tab         |
| Open File/Edit/View/Help menu | Alt+F / Alt+E / Alt+V / Alt+H |
| Quit                  | Ctrl+Q            |

There's also *Help → About* for version and project information.

See [MAINTENANCE.md](MAINTENANCE.md) for architecture and maintainer notes.
