# MAINTENANCE.md

Technical notes for anyone (human or AI) maintaining `qdvc_markdown_notebook.py`.

## 1. Overview

A small GTK 3 / PyGObject desktop application. No build step, no external Python
dependencies beyond `gi` (PyGObject). It edits markdown files **in place** on
disk; there is no database, index, or cache.

The code is organised as a thin entry-point script plus an internal package,
following an MVC-flavoured layering (adapted for GTK, where view and controller
are necessarily intertwined):

```
qdvc_markdown_notebook.py        # entry point: argv parsing, builds window, Gtk.main()
qdvcmdnb_lib/
    __init__.py
    config.py                    # constants, sort modes, ALL_NOTES sentinel (no GTK, no I/O)
    settings.py                  # persistent user settings: YAML under ~/.config (no GTK)
    model.py                     # data layer: Note + filesystem + disk I/O (no GTK)
    highlighter.py               # MarkdownHighlighter (GTK TextBuffer tagging)
    editortab.py                 # EditorTab: one tab's editor widget + state
    preferences.py               # PreferencesDialog: fonts + toolbar style
    window.py                    # NotebookWindow: view + controller
```

The key boundary: **`window.py` never touches the filesystem directly.** All
disk reads/writes/creation go through `model.py`. `config.py` and `model.py`
import no GTK at all and are unit-testable without a display.

Run modes:

```bash
python3 qdvc_markdown_notebook.py /path/to/data   # sys.argv[1] = root folder
python3 qdvc_markdown_notebook.py                 # empty; user opens via Ctrl+O
```

Run from the directory containing both the script and `qdvcmdnb_lib/` (the
script imports the package by name).

## 2. Runtime dependencies

- Python 3.6+ (uses f-strings; the walrus `:=` in the highlighter needs 3.8+).
- PyGObject with GTK 3 typelibs: `python3-gi`, `gir1.2-gtk-3.0`.
- `Pango`, `Gdk`, `GLib`, `Gio` come with the GTK 3 introspection data.
- **PyYAML** — *optional*. Used only by `settings.py` to persist user settings.
  If it is missing the app still runs with default settings; nothing is saved
  and a one-line warning is printed to stderr. Install with `pip install pyyaml`
  (Debian/MATE: `sudo apt install python3-yaml`).

There is **no** markdown-rendering library (e.g. `markdown`, `mistune`). This is
intentional: the spec requires a monospace view with no font-size variation, so
highlighting is done with regexes against a `Gtk.TextBuffer` and tag table.

## 3. Architecture

Five logical parts, one per module:

### 3.0 `config.py`
Plain constants only — `APP_NAME`, `MARKDOWN_EXTENSIONS`, the `SORT_*` mode
strings, and the `ALL_NOTES` sentinel. No GTK, no I/O, so it is safe to import
from anywhere. `ALL_NOTES` is an `object()`; compare with `is`, never `==`.

### 3.0a `settings.py` — persistent user settings (no GTK)
- Stores settings as YAML at `$XDG_CONFIG_HOME/qdvcmdnb/config.yml`, falling back
  to `~/.config/qdvcmdnb/config.yml`. Resolve via `config_dir()` / `config_path()`.
- `Settings` holds `editor_font` and `code_font` (both Pango font-description
  strings), `toolbar_style` (`"below"` or `"beside"`, the `TOOLBAR_TEXT_*`
  constants), and `recent_folders` (most-recent-first list, capped at
  `MAX_RECENT`). `editor_font` themes the whole editor; `code_font` is applied to
  inline code and fenced code blocks only (see the highlighter); `toolbar_style`
  controls whether toolbar button text sits below or beside the icon. Construct
  via `Settings.load()`, which returns sane defaults on a missing/malformed file
  or any read error — it never raises to the caller.
- `save()` writes atomically (temp file + `os.replace`) and returns a bool.
- `add_recent_folder()` dedups (moves existing to front), prunes directories that
  no longer exist, and caps the list.
- **PyYAML is optional.** If `import yaml` fails, `_HAVE_YAML` is False: `load()`
  returns defaults, `save()` is a no-op returning False, and a single stderr
  warning is emitted (guarded by `_warned_no_yaml`). The app remains usable.
- **Forward compatibility:** unrecognised top-level keys in the file are stashed
  in `Settings._extra` and re-emitted on `save()`, so a newer build's settings
  survive a round-trip through an older one. Bump `SCHEMA_VERSION` for real
  migrations and add handling in `_apply()`.
- No GTK import — unit-testable headless.

### 3.1 `highlighter.py` — `MarkdownHighlighter`
- Owns the editor `Gtk.TextBuffer`'s tag table and applies colour/weight tags.
- `_make_tags()` defines tags once (idempotent via `table.lookup`).
- `highlight()` clears all tags over the whole buffer and re-applies them. It is
  **whole-buffer**, called on every `changed` signal. Fine for note-sized files;
  if you need to support very large files, switch to highlighting only the
  changed line range (track via the buffer's `insert-text`/`delete-range`).
- Fenced code blocks (```` ``` ````) are tracked with the `in_fence` toggle as
  lines are scanned in order. Line-level rules (headings, blockquotes, lists,
  hr) and inline rules (inline code, bold, italic, links) are separate lists of
  `(tag_name, compiled_regex, group)` tuples.
- Offsets: the buffer text is split on `\n`; `offset` tracks the character index
  of each line start, `+1` per line for the stripped newline. If you change the
  splitting, keep this accounting correct or tags will land on wrong ranges.
- Code font: the `code_inline` and `code_block` tags no longer hard-code
  `family="monospace"`. `set_code_font(desc)` sets the tags' `font` property
  (a full Pango font-description string, e.g. "Fira Code 10"), so the user's
  *View → Set Code Font* choice fully controls code-span family and size while
  the rest of the editor uses `editor_font`. The constructor takes `code_font`
  and applies it immediately, so already-loaded text reflects the font.

### 3.2 `model.py` — data layer (no GTK)
- `Note` — a thin wrapper over a file path; caches `name` and `mtime`.
  `display_name()` strips a known markdown extension for the list label.
- `is_markdown(filename)` — extension check against `MARKDOWN_EXTENSIONS`.
- `collect_notes(folder)` — recursive `os.walk`; returns all markdown files at
  **any** depth. This is how both "All Notes" and the per-subfolder view get
  their contents, which implements the spec's "aggregate deeper levels to the
  parent subfolder" rule: selecting a top-level subfolder shows everything under
  it recursively.
- `immediate_subfolders(root)` — only **one** level down, hidden dirs excluded.
- `sort_notes(notes, sort_mode)` — returns a new sorted list per the `SORT_*`
  mode. (Moved out of the window during the refactor so sorting is testable.)
- Disk I/O: `read_note`, `write_note`, `unique_note_path`, `create_empty_note`.
  These **raise** `OSError`/`UnicodeDecodeError` on failure; the window catches
  and shows the error dialog. `write_note` refreshes the note's `mtime`. Writes
  are not atomic (see §6).
- Slug/rename (for the Slugify toolbar button): `heading_for_slug(text)` returns
  the level-1 heading content if `text`'s first line is `# …` and the heading is
  **< 32** chars (`SLUG_MAX_HEADING_LEN`), else `None`. `slugify(heading)` lowers
  the text and collapses every run of non-`[a-z]` characters to a single dash,
  stripping leading/trailing dashes (so `"My awesome new note!"` →
  `"my-awesome-new-note"`; digits and punctuation are dropped). `rename_note(note,
  base)` renames the file in place within its folder, using `unique_note_path` to
  avoid collisions, and updates the `Note`'s `path`/`name`; it is a no-op if the
  name is already correct. All three are pure/testable; the heading check reads
  the tab's **live** buffer, not the file on disk.

### 3.2a `editortab.py` — `EditorTab`
Encapsulates one tab's editor state, which previously lived directly on the
window. Each `EditorTab` owns its own `Gtk.TextView`, `Gtk.TextBuffer`,
`MarkdownHighlighter`, the `note` open in it (or `None`), and per-tab `dirty` /
`_loading` flags.
- `widget` — the page widget added to the `Gtk.Notebook`. It is a `Gtk.Stack`
  with two named children: `"editor"` (a scrolled `TextView`) and `"placeholder"`
  (a centred dim "Select a note…" message). `_update_view_mode()` shows the
  placeholder when `note is None`, else the editor; it is called from `clear()`
  and `load_note()`. A fresh Ctrl+T tab therefore shows the placeholder until a
  note is loaded.
- `tab_label` — a horizontal box: a title label + a borderless close button
  (Caja-style, `window-close` icon at `MENU` size). The title is the note's
  display name, truncated to `MAX_TAB_TITLE` (12) characters with a trailing
  ellipsis when longer; a leading `*` marks unsaved changes. Truncation is done
  in `_refresh_title()` on the string itself (not via Pango width-ellipsize, which
  depended on allocated width and could clip even short names).
- Callbacks passed in by the window: `on_changed(tab)` (buffer edited, not during
  a programmatic load) and `on_close(tab)` (close button clicked).
- API: `load_note(note)` → bool, `save()` → bool (both return False on I/O error
  and leave the dialog to the caller), `clear()`, `get_content()`,
  `apply_font(str)`, `apply_code_font(str)`, `title_text()`. The constructor
  takes `code_font` and forwards it to the highlighter.
- The dirty marker is a leading `*` on the tab title, refreshed by
  `_refresh_title()`.
- `_loading` guards the buffer `changed` signal during programmatic text sets,
  exactly as the single-editor version did — but now per tab.

### 3.2b `preferences.py` — `PreferencesDialog`
A modal `Gtk.Dialog` (GNOME2/MATE idiom: "Preferences" under the **Edit** menu).
Two sections: a Fonts frame with two `Gtk.FontButton`s (editor + code), and a
Toolbar frame with a radio pair (text below vs beside icons). It has **Save** and
**Cancel** buttons. Each control change applies **live** (mutates the shared
`Settings` in memory and calls the window's `on_apply` to re-theme), but is *not*
persisted until Save. The dialog snapshots the original values on open
(`_original`); `run_modal()` runs the dialog and, on Save, calls
`settings.save()`, while on Cancel/close it restores the snapshot and re-applies
(reverting the live preview). The window calls `dialog.run_modal()` rather than
just constructing it. This module replaced the former *View → Set Editor Font* /
*Set Code Font* menu items.

### 3.3 `window.py` — `NotebookWindow` (view + controller)
The editor area is now a `Gtk.Notebook` of `EditorTab` pages; `self._tabs` is a
list kept parallel to the notebook pages. Most editor operations delegate to the
**active tab** via `_active_tab()`.

On startup the window centers itself (`set_position(CENTER)`) and sets its icon
name to `accessories-text-editor`; the entry point also calls
`Gtk.Window.set_default_icon_name(...)` and `GLib.set_prgname(...)` so the
panel/taskbar can match the window to the `.desktop` file (its `StartupWMClass`).

Menu items use `_icon_menu_item(label, icon_name)`, which builds a
`Gtk.ImageMenuItem` (deprecated in GTK3 but the idiomatic MATE-era way to show
icons in menus; it falls back to a plain `MenuItem`). Icons are stock freedesktop
names: New=`document-new`, Save=`document-save`, Open Working Folder=`folder-open`,
Open Recent=`document-open-recent`, New Tab=`tab-new`, Quit=`application-exit`,
Preferences=`preferences-system`, About=`help-about`. Plain items (Close Tab, the
sort radio items) intentionally have no icon, per HIG restraint.

Tab navigation (`_on_key_press`, connected to the window's `key-press-event`):
Ctrl+Tab → `_cycle_tab(forward=True)`, Ctrl+Shift+Tab → backward (GTK sends
`ISO_Left_Tab` for shifted Tab, which is handled), and Alt+1..9 → `_goto_tab`.
Both helpers wrap/clamp safely and no-op when the index is out of range. These use
a raw key handler rather than accelerators because Tab is otherwise consumed by
focus navigation.

Key state attributes:
- `root_folder` — absolute path of the open data folder, or `None`.
- `current_subfolder` — either the sentinel `ALL_NOTES` or a subfolder **name**
  (relative to `root_folder`).
- `_tabs` — list of `EditorTab`, parallel to notebook pages.
- `sort_mode` — one of `SORT_ALPHA`, `SORT_DATE_NEW`, `SORT_DATE_OLD`.
- `_note_select_guard` — suppresses the note-list `changed` handler while the
  window programmatically restores a selection (used by `_reselect_active_note`
  after a cancelled note switch), preventing a reload feedback loop.
- `settings` — the loaded `Settings` instance (see §3.0a).

Per-tab dirty/loading/note state lives on each `EditorTab`, not on the window.

Tab wiring:
- `_new_tab(focus)` builds an `EditorTab`, applies the font, appends it to the
  notebook and `_tabs`, updates tab-bar visibility, and optionally switches to it.
- `_close_tab(tab)` is a **no-op when only one tab remains** (per spec). Otherwise
  it prompts via `_maybe_warn_unsaved(tab)` then removes the page and list entry.
- `_update_tabbar_visibility()` calls `notebook.set_show_tabs(len(_tabs) > 1)`,
  which is what makes the whole tab bar vanish at one tab.
- `_active_tab()` maps the notebook's current page index to `_tabs`.
- Ctrl+T → `on_new_tab`; Ctrl+W → `on_close_tab` (both also menu items under
  File). Right-click in the note list → `on_notelist_button_press` builds a popup
  with "Open in new tab", "Copy full path", and "Show in file browser".
- Quitting/closing the window runs `_confirm_close_all`, which prompts for *every*
  dirty tab before exit.

Menus: **File** (New, Save, Open Working Folder, Open Recent, New Tab, Close Tab,
Quit), **View** (the three sort modes — font items were removed), **Edit**
(Preferences), **Help** (About). `on_preferences` opens the `PreferencesDialog`
with `_apply_preferences` as its callback; `on_about` shows a `Gtk.AboutDialog`.

Settings wiring: `__init__` calls `Settings.load()`, then after `_build_ui()`
calls `_apply_editor_font()`, `_apply_code_font()`, and `_rebuild_recent_menu()`.
`open_folder()` calls `_remember_folder()` (which records, saves, and refreshes
the Open Recent menu). Font and toolbar-style changes now flow through the
Preferences dialog, whose `on_apply` callback (`_apply_preferences`) re-applies
the editor font, code font, and toolbar style to the live UI. `_apply_editor_font`
and `_apply_code_font` iterate **all** tabs; `_apply_toolbar_style` maps
`settings.toolbar_style` to a `Gtk.ToolbarStyle` (`BOTH` = below, `BOTH_HORIZ` =
beside) via `_toolbar_style_enum()`. `on_open_recent` opens a folder from the menu
(handling the case where it has since been deleted).

Note: inside the selection handlers the local variable for the GTK model is
named `model_` (trailing underscore) to avoid shadowing the imported `model`
module.

UI is built in `_build_*` methods and assembled in `_build_ui()`:
- Layout: `vbox` → menubar, toolbar, then nested `Gtk.Paned`
  (`outer` horizontal holds sidebar + `inner`; `inner` holds note list + editor),
  then statusbar. Pane positions set with `set_position`.
- Sidebar: `Gtk.TreeStore(str, str, str, bool)` = (icon-name, label,
  subfolder-name, is_all). The column packs a `CellRendererPixbuf` (icon-name
  attribute → column 0) before the text renderer (→ column 1). Icons are
  freedesktop names: `emblem-documents` for All Notes, `folder` for subfolders.
  **Beware the index shift:** `is_all` is column **3**, subfolder name column
  **2** (they were 2 and 1 before the icon column was added) — selection handlers
  read those indices.
- Toolbar: built in `_build_toolbar`, style from `_toolbar_style_enum()`. Buttons:
  New note, Save note, and **Slugify** (`btn_slugify`). Slugify starts insensitive
  and is enabled/disabled by `_update_slugify_sensitivity()` (called from
  `update_status`, so it re-evaluates on edits, tab switches, and loads): enabled
  only when the active tab has a note and its live first line is a short H1 that
  yields a non-empty slug. `on_slugify` renames via `model.rename_note`, refreshes
  the tab title, and reloads the list selecting the new path.
- Note list: `Gtk.ListStore(str, str, float)` = (display name, full path, mtime).
- Editor: a `Gtk.Notebook`; each page is an `EditorTab` (see §3.2a). `editor_font`
  themes the whole view; `code_font` themes code spans via the highlighter tags.
  Keep a single uniform size for body text — do not introduce size-varying tags.

## 4. Control flow

- Selecting a sidebar row → `on_sidebar_selection_changed` sets
  `current_subfolder` and reloads the note list. (It no longer clears the editor;
  tabs keep their own content.)
- Selecting a note (single click) → `on_note_selection_changed` checks the active
  tab for unsaved changes (cancelling restores the prior selection via
  `_reselect_active_note`), then `_load_note_in_active_tab` **replaces** the
  active tab's content.
- Right-click a note → `on_notelist_button_press` builds a popup with: "Open in
  new tab" (`_load_note_in_new_tab`), "Copy full path" (`_copy_path_to_clipboard`
  via the `CLIPBOARD` selection), and "Show in file browser"
  (`_show_in_file_browser`, which converts the parent dir to a `file://` URI with
  `GLib.filename_to_uri` and opens it via `Gtk.show_uri_on_window`).
- Typing → the tab's own `_buffer_changed` sets its `dirty` flag, re-highlights,
  updates the tab title, and calls back to the window (`_on_tab_changed` →
  `update_status`, which also re-evaluates Slugify sensitivity).
- New note → `on_new_note` writes an empty file into the current subfolder (or
  root if All Notes is selected) via `model.create_empty_note`, reloads the list,
  and opens it in the active tab.
- Slugify → `on_slugify` reads the active tab's live content, derives a slug from
  its H1, **confirms via `_confirm`** (an OK/Cancel `MessageDialog`), then renames
  via `model.rename_note` and refreshes title + list. The button is only sensitive
  when those conditions hold (see §3.3 toolbar).
- New tab (Ctrl+T) → `on_new_tab` → `_new_tab(focus=True)`.
- Switch tabs → Ctrl+Tab / Ctrl+Shift+Tab cycle; Alt+1..9 jump (via
  `_on_key_press`).
- Close tab (Ctrl+W / close button) → `on_close_tab` / the tab's close callback →
  `_close_tab`, a no-op at one tab.
- Save → `_save_active` writes the active tab's content to its note.
- Sort change → `on_sort_changed` reloads the list, keeping the active tab's note
  selected by path.
- Preferences → `on_preferences` opens the dialog and calls `run_modal`; live
  changes preview via `_apply_preferences`, Save persists, Cancel reverts.
- About → `on_about` shows a `Gtk.AboutDialog`.
- Quit / window close → `_confirm_close_all` prompts for each dirty tab.

## 5. Known deviations from the original spec

- **Quit shortcut.** The spec listed `Ctrl+S` for both Save and Quit. That is a
  collision, so Quit is bound to the conventional **Ctrl+Q**. If you truly want
  Ctrl+S for Quit, change the accelerator on `mi_quit` — but you'll lose Save.
- **Rename.** There is no free-form rename UI; renaming happens via **Slugify**,
  which derives the filename from the note's H1. New notes start as `Untitled.md`,
  `Untitled 1.md`, … A general inline-rename remains a natural next feature (§7).
- **Desktop integration.** The app ships no installer; the `.desktop` file is set
  up by hand (see README). `Icon=accessories-text-editor` is a stock freedesktop
  icon present on typical GNOME/MATE installs.

## 6. Gotchas

- `_loading` must wrap **every** programmatic `set_text`. Forgetting it will
  flip `_dirty` and trigger a re-highlight loop feel.
- `current_subfolder` stores a **name**, not a path; join with `root_folder`
  before touching disk. `ALL_NOTES` is an `object()` sentinel — compare with
  `is`, never `==`.
- The note list dedupes nothing: if two subfolders contain identically named
  files, "All Notes" shows both (correct — different paths).
- Highlighting clears and re-tags the whole buffer each keystroke. If profiling
  shows lag on large files, scope it to the edited line range.
- File writes are not atomic. A crash mid-write could truncate a note. If
  robustness matters, write to a temp file and `os.replace`.

## 7. Suggested next features

- Free-form rename note (inline edit in the list; `model.rename_note` already
  exists, so this is mostly UI).
- Delete note (with confirmation; move to trash via `Gio.File.trash`).
- Live full-text search box above the note list (filter `note_store`).
- File-system watch (`Gio.FileMonitor`) to auto-refresh on external changes.
- Per-note word/char count in the status bar.
- Remember last folder and window geometry (e.g. as more keys in the settings
  YAML).

## 8. Testing

There is no formal test suite yet, but the refactor makes the model layer
testable without a display, since `config.py` and `model.py` import no GTK.

Syntax-check everything:

```bash
python3 -m py_compile qdvc_markdown_notebook.py qdvcmdnb_lib/*.py
```

The data layer can be exercised directly, e.g.:

```python
from qdvcmdnb_lib import model, config
notes = model.collect_notes("/some/folder")
ordered = model.sort_notes(notes, config.SORT_DATE_NEW)
```

This is a good place to add a real `tests/` directory (pytest) covering
`collect_notes`, `immediate_subfolders`, `sort_notes`, the
`unique_note_path`/`create_empty_note`/`read_note`/`write_note` roundtrip, and the
`heading_for_slug`/`slugify`/`rename_note` helpers — none of which need GTK.

Manual smoke test (needs GTK installed):

1. Launch with a sample folder; confirm sidebar lists subfolders one level deep.
2. Select All Notes vs a subfolder; confirm counts in the status bar.
3. Create, edit, save a note; reopen to confirm persistence.
4. Switch sort modes; confirm ordering and that the open note stays selected.
5. Edit without saving, then switch notes / quit; confirm the unsaved prompt.
