# MAINTENANCE.md

Technical notes for anyone (human or AI) maintaining `qdvc_markdown_notebook.py`.

## 1. Overview

Single-file GTK 3 / PyGObject desktop application. No build step, no package,
no external Python dependencies beyond `gi` (PyGObject). It edits markdown files
**in place** on disk; there is no database, index, or cache.

Run modes:

```bash
python3 qdvc_markdown_notebook.py /path/to/data   # sys.argv[1] = root folder
python3 qdvc_markdown_notebook.py                 # empty; user opens via Ctrl+O
```

## 2. Runtime dependencies

- Python 3.6+ (uses f-strings; the walrus `:=` in the highlighter needs 3.8+).
- PyGObject with GTK 3 typelibs: `python3-gi`, `gir1.2-gtk-3.0`.
- `Pango`, `Gdk`, `GLib`, `Gio` come with the GTK 3 introspection data.

There is **no** markdown-rendering library (e.g. `markdown`, `mistune`). This is
intentional: the spec requires a monospace view with no font-size variation, so
highlighting is done with regexes against a `Gtk.TextBuffer` and tag table.

## 3. Architecture

The whole program lives in one module. Three logical parts:

### 3.1 `MarkdownHighlighter`
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

### 3.2 Data model
- `Note` — a thin wrapper over a file path; caches `name` and `mtime`.
  `display_name()` strips a known markdown extension for the list label.
- `MARKDOWN_EXTENSIONS` — the set of recognised extensions (includes `.txt`).
- `collect_notes(folder)` — recursive `os.walk`; returns all markdown files at
  **any** depth. This is how both "All Notes" and the per-subfolder view get
  their contents, which implements the spec's "aggregate deeper levels to the
  parent subfolder" rule: selecting a top-level subfolder shows everything under
  it recursively.
- `immediate_subfolders(root)` — only **one** level down, hidden dirs excluded.

### 3.3 `NotebookWindow` (the controller + view)
Key state attributes:
- `root_folder` — absolute path of the open data folder, or `None`.
- `current_subfolder` — either the sentinel `ALL_NOTES` or a subfolder **name**
  (relative to `root_folder`).
- `current_note` — the `Note` open in the editor, or `None`.
- `sort_mode` — one of `SORT_ALPHA`, `SORT_DATE_NEW`, `SORT_DATE_OLD`.
- `_dirty` — unsaved-changes flag.
- `_loading` — guard set while programmatically setting buffer text so the
  `changed` handler doesn't mark the buffer dirty or re-highlight spuriously.

UI is built in `_build_*` methods and assembled in `_build_ui()`:
- Layout: `vbox` → menubar, toolbar, then nested `Gtk.Paned`
  (`outer` horizontal holds sidebar + `inner`; `inner` holds note list + editor),
  then statusbar. Pane positions set with `set_position`.
- Sidebar: `Gtk.TreeStore(str, str, bool)` = (label, subfolder-name, is_all).
- Note list: `Gtk.ListStore(str, str, float)` = (display name, full path, mtime).
- Editor: `Gtk.TextView` with `set_monospace(True)` **and** an explicit
  `override_font(Pango.FontDescription("monospace 11"))` to guarantee a single
  uniform size. Do not introduce size-varying tags — the spec forbids it.

## 4. Control flow

- Selecting a sidebar row → `on_sidebar_selection_changed` sets
  `current_subfolder`, clears editor, reloads the note list.
- Selecting a note → `on_note_selection_changed` checks for unsaved changes,
  then `_load_note` reads the file and highlights it.
- Typing → `on_text_changed` sets `_dirty`, re-highlights, updates status.
- New note → `on_new_note` writes an empty file into the current subfolder
  (or root if All Notes is selected), via `_unique_note_path` to avoid clobber,
  reloads the list, selects and opens the new file.
- Save → `_save_current` writes the buffer to `current_note.path`.
- Sort change → `on_sort_changed` reloads the list, attempting to keep the
  current note selected by path.

## 5. Known deviations from the original spec

- **Quit shortcut.** The spec listed `Ctrl+S` for both Save and Quit. That is a
  collision, so Quit is bound to the conventional **Ctrl+Q**. If you truly want
  Ctrl+S for Quit, change the accelerator on `mi_quit` — but you'll lose Save.
- **No rename UI yet.** New notes are created as `Untitled.md`,
  `Untitled 1.md`, … Renaming is a natural next feature (see §7).

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

- Rename note (inline edit in the list; `os.rename` + reload).
- Delete note (with confirmation; move to trash via `Gio.File.trash`).
- Live full-text search box above the note list (filter `note_store`).
- File-system watch (`Gio.FileMonitor`) to auto-refresh on external changes.
- Per-note word/char count in the status bar.
- Remember last folder and window geometry (e.g. via `GLib.KeyFile` in
  `$XDG_CONFIG_HOME`).

## 8. Testing

There is no automated test suite. Minimum manual smoke test:

1. `python3 -m py_compile qdvc_markdown_notebook.py` — syntax check.
2. Launch with a sample folder; confirm sidebar lists subfolders one level deep.
3. Select All Notes vs a subfolder; confirm counts in the status bar.
4. Create, edit, save a note; reopen to confirm persistence.
5. Switch sort modes; confirm ordering and that the open note stays selected.
6. Edit without saving, then switch notes / quit; confirm the unsaved prompt.
