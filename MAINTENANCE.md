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
strings, the `ALL_NOTES` sentinel, and the sidebar `NODE_*` kind strings
(`NODE_ALL_NOTES`, `NODE_EMPTY_NOTES`, `NODE_SUBFOLDERS`, `NODE_SUBFOLDER`). No
GTK, no I/O, so it is safe to import from anywhere. `ALL_NOTES` is an `object()`;
compare with `is`, never `==`. (`ALL_NOTES` predates the tree sidebar; the sidebar
now uses the `NODE_*` kinds instead.)

### 3.0a `settings.py` — persistent user settings (no GTK)
- Stores settings as YAML at `$XDG_CONFIG_HOME/qdvcmdnb/config.yml`, falling back
  to `~/.config/qdvcmdnb/config.yml`. Resolve via `config_dir()` / `config_path()`.
- `Settings` holds `editor_font`, `code_font`, and `preview_font` (Pango
  font-description strings), `editor_line_spacing` and `preview_line_spacing`
  (ints, pixels of extra inter-line space, clamped to `[MIN_LINE_SPACING,
  MAX_LINE_SPACING]` via `_coerce_spacing`), `toolbar_style` (`"below"` or
  `"beside"`, the `TOOLBAR_TEXT_*` constants), and `recent_folders`
  (most-recent-first list, capped at `MAX_RECENT`). `editor_font` themes the
  editor; `code_font` themes inline/fenced code in both the editor (highlighter)
  and the preview; `preview_font` is the preview body font; the two spacings apply
  to the editor and preview views. Construct via `Settings.load()`, which returns
  sane defaults on a missing/malformed file or any read error — it never raises to
  the caller.
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

### 3.1a `pango_markdown.py` — Markdown → Pango markup (no GTK)
`render(text, code_font=None)` converts a Markdown subset to a Pango markup string
for Preview mode (no WebKit). Pango markup is inline-only (`<b>`, `<i>`, `<tt>`,
`<span>`, size/weight/foreground), so block structure is approximated: headings
become sized+bold spans, lists get bullet/number prefixes with indentation,
blockquotes a `\u2503` bar + italics, fenced/inline code with a grey background,
horizontal rules a line of dashes, links the underlined coloured text (the URL is
dropped — markup can't make clickable links). When `code_font` (a Pango
font-description string) is supplied, code spans/blocks use it via
`<span font_desc=...>`; otherwise they fall back to `<tt>` (generic monospace).
Attribute values are quote-escaped (`_attr_escape`) so a font name with an
apostrophe can't break the markup. All text is XML-escaped first, and code is
escaped but not further interpreted. The output is always well-formed markup. Pure
text→text, no GTK, so it is unit-testable. Deliberately lightweight (same "good
enough" philosophy as the highlighter), not a full CommonMark parser.

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
- `note_is_empty(note)` / `collect_empty_notes(folder)` — for the sidebar's
  *Empty Notes* node. A note is "empty" if its content `.strip()`s to `""`.
  Unreadable files are treated as not-empty (so they aren't silently hidden).
- `note_matches(note, query_lower)` / `filter_notes(notes, query)` — for the
  note-list search. Matching is case-insensitive against the note's display name
  **and its full file contents** (read on demand). A blank/None query returns the
  list unchanged. Unreadable files fall back to name-only matching, so a transient
  read error doesn't make a note disappear from results.
- `sort_notes(notes, sort_mode)` — returns a new sorted list per the `SORT_*`
  mode. (Moved out of the window during the refactor so sorting is testable.)
- Disk I/O: `read_note`, `write_note`, `unique_note_path`, `create_empty_note`.
  These **raise** `OSError`/`UnicodeDecodeError` on failure; the window catches
  and shows the error dialog. `write_note` refreshes the note's `mtime`. Writes
  are not atomic (see §6).
- Card-view helpers: `first_body_line(note)` returns the first non-blank line
  after a leading heading (skips one `#`..`######` line; if no heading, the first
  non-blank line), or `""` on empty/unreadable; `format_mtime_value(mtime)` formats
  a raw mtime float as `YYYY-MM-DD HH:MM` (or `""` if 0), and `format_mtime(note)`
  delegates to it. The window's cell-data-func uses the float form (it only has the
  store's mtime column at draw time).
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
  with three named children: `"editor"` (a scrolled `TextView`), `"preview"` (a
  read-only `TextView` showing rendered markdown), and `"placeholder"` (a centred
  dim "Select a note…" message). `_update_view_mode()` picks the child: placeholder
  when `note is None`, else `"preview"` when `self.preview`, else `"editor"`. It is
  called from `clear()`, `load_note()`, and `set_preview()`. A fresh Ctrl+T tab
  shows the placeholder until a note is loaded.
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
  `apply_font(str)`, `apply_code_font(str)` (also re-renders the preview if
  active), `apply_preview_font(str)` (preview body font), `apply_editor_line_spacing(px)`
  / `apply_preview_line_spacing(px)` (set `pixels_below_lines` + `pixels_inside_wrap`
  on the editor/preview views), `set_editable(bool)` (read-only mode; toggles
  `TextView.set_editable`/`set_cursor_visible`), `set_preview(bool)` (renders
  current content via `pango_markdown.render(..., code_font=self._code_font)` into
  the preview buffer with `insert_markup`, then switches the stack),
  `highlight_search(query)` (see below), `title_text()`. The constructor takes
  `code_font` and forwards it to the highlighter; the tab caches it for preview
  rendering.
- Search highlight (#5): a dedicated `search_match` tag (yellow `#fff176`
  background) is created on the buffer. `highlight_search(query)` stores the query
  and `_apply_search_highlight()` clears the tag then re-applies it to every
  case-insensitive occurrence in the editor text; a blank/None query just clears.
  It is re-applied after `load_note` and on every buffer change so the spans track
  edits. The highlight is independent of the markdown highlighter's own tags.
- Preview re-renders on `load_note` when already active; in preview the editor is
  hidden and content can't change, so no live re-render is needed while previewing.
- The dirty marker is a leading `*` on the tab title, refreshed by
  `_refresh_title()`.
- `_loading` guards the buffer `changed` signal during programmatic text sets,
  exactly as the single-editor version did — but now per tab.

### 3.2b `preferences.py` — `PreferencesDialog`
A modal `Gtk.Dialog` (GNOME2/MATE idiom: "Preferences" under the **Edit** menu)
with a `Gtk.Notebook` of two tabs. **Fonts**: `Gtk.FontButton`s for editor font,
code font, and markdown-preview font, plus two `Gtk.SpinButton`s for editor and
preview line spacing (range `MIN_LINE_SPACING`..`MAX_LINE_SPACING`). **Interface**:
a radio pair for toolbar text below vs beside icons. It has **Save** and **Cancel**
buttons. Each control change applies **live** (mutates the shared `Settings` in
memory and calls the window's `on_apply` to re-theme), but is *not* persisted until
Save. The dialog snapshots all original values on open (`_original`); `run_modal()`
runs the dialog and, on Save, calls `settings.save()`, while on Cancel/close it
restores the snapshot (all six fields) and re-applies (reverting the live preview).
The window calls `dialog.run_modal()` rather than just constructing it.

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
names: New note=`document-new`, Save note=`document-save`, Open
workspace=`folder-open`, Open recent workspace=`document-open-recent`, New
tab=`tab-new`, Quit=`application-exit`, Preferences=`preferences-system`,
About=`help-about`. Plain items (Close workspace, Close tab, the View toggles, and
the sort radio items) intentionally have no icon, per HIG restraint.

Tab navigation (`_on_key_press`, connected to the window's `key-press-event`):
Ctrl+Tab → `_cycle_tab(forward=True)`, Ctrl+Shift+Tab → backward (GTK sends
`ISO_Left_Tab` for shifted Tab, which is handled), and Alt+1..9 → `_goto_tab`.
Both helpers wrap/clamp safely and no-op when the index is out of range. These use
a raw key handler rather than accelerators because Tab is otherwise consumed by
focus navigation.

Key state attributes:
- `root_folder` — absolute path of the open data folder, or `None`.
- `current_node` — the selected sidebar node kind (a `NODE_*` constant).
- `current_subfolder` — the subfolder **name** when `current_node` is
  `NODE_SUBFOLDER`, else `None`.
- `read_only` — whether editing is disabled across all tabs (starts `True`).
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

Read-only mode (toolbar toggle, default on): `self.read_only` is the single source
of truth, applied by `_apply_read_only()` which calls `tab.set_editable(...)` on
every tab and refreshes the status bar. `_new_tab` seeds new tabs from it.
`on_toggle_read_only` flips it from the `Gtk.ToggleToolButton`. Edit actions are
gated on it: New note shows a notice and aborts, and Slugify is desensitised in
`_update_slugify_sensitivity`. Saving is left allowed (a read-only buffer cannot
have changed, so it is harmless).

Preview mode (toolbar toggle, default off): `self.preview_mode` is window-wide,
applied by `_apply_preview()` which calls `tab.set_preview(...)` on every tab,
**disables the Read-only toggle** (`btn_readonly.set_sensitive(False)`) so it
can't be changed while previewing, and refreshes the status bar. `_new_tab` seeds
new tabs from it. `on_toggle_preview` flips it from the `Gtk.ToggleToolButton`.
In `update_status` the bold mode label shows "Rendered Markdown preview" when
`preview_mode` is on, overriding the read-only/edit label; otherwise it shows
"Read-only mode" / "Edit mode" as before. Preview is always read-only by
construction (the preview `TextView` is non-editable), independent of
`self.read_only`.

Menus (order **File, Edit, View, Help**): **File** (New note, Save note, Open
workspace, Close workspace, Open recent workspace, New tab, Close tab, Quit, with
two separators per the layout), **Edit** (Preferences), **View** (Toolbar and
Statusbar `Gtk.CheckMenuItem` toggles, a separator, then the three sort
`RadioMenuItem`s), **Help** (About). `on_close_workspace` resets to the empty
initial state (after `_confirm_close_all`); `on_toggle_toolbar` /
`on_toggle_statusbar` flip `self.toolbar` / `self.statusbar_box` visibility (both
checks default on). `on_preferences` opens the `PreferencesDialog`; `on_about`
shows a `Gtk.AboutDialog`. The four top-level items are created with
`Gtk.MenuItem.new_with_mnemonic("_File"/"_Edit"/"_View"/"_Help")`, so Alt+F/E/V/H
open the respective menus.

Settings wiring: `__init__` calls `Settings.load()`, then after `_build_ui()`
calls `_apply_editor_font()`, `_apply_code_font()`, `_apply_preview_font()`,
`_apply_line_spacing()`, and `_rebuild_recent_menu()`. `open_folder()` calls
`_remember_folder()` (which records, saves, and refreshes the recent-workspace
menu). Font, spacing, and toolbar-style changes flow through the Preferences
dialog, whose `on_apply` callback (`_apply_preferences`) re-applies the editor
font, code font, preview font, line spacings, and toolbar style to the live UI.
`_apply_editor_font` / `_apply_code_font` / `_apply_preview_font` /
`_apply_line_spacing` iterate **all** tabs; `_apply_toolbar_style` maps
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
- Sidebar: `Gtk.TreeStore(str, str, str, str)` = (icon-name, label, node-kind,
  subfolder-name). A `CellRendererPixbuf` (icon-name → column 0) precedes the text
  renderer (label → column 1). Built by `_reload_sidebar` as a **tree**: top-level
  rows for *All Notes* (`emblem-documents`), *Empty Notes* (`edit-clear`), and
  *Subfolders* (`folder`); each immediate subfolder is a child of the Subfolders
  row (`NODE_SUBFOLDER`, label and column-3 = its name). `expand_all()` keeps the
  branch open. `on_sidebar_selection_changed` switches on the node kind (column 2):
  All/Empty/subfolder reload the list; the Subfolders **parent** shows placeholders
  in both panes (`_show_notelist_placeholder` + `tab.clear()`).
- Toolbar: built in `_build_toolbar`, style from `_toolbar_style_enum()`. Order:
  **New note**, **Save note** (`btn_save`, `document-save`; starts insensitive and
  is enabled only when the active tab is dirty — `_update_save_sensitivity()`,
  called from `update_status`), **Refresh note** (`btn_refresh`, `view-refresh`;
  `on_refresh_note` reloads the active tab's note from disk via a fresh
  `model.Note`, after `_maybe_warn_unsaved` — same prompt as closing a tab;
  sensitive whenever a note is open), **Slugify** (`btn_slugify`, insensitive unless
  the active tab's live first line is a short H1 in edit mode, per
  `_update_slugify_sensitivity()`), `|` separator, **Card view** (`btn_cardview`,
  `mail-attachment` icon, off by default — `on_toggle_card_view` flips
  `self.card_view`, calls `_apply_card_view()`, and reloads keeping selection), `|`
  separator, **Read-only** (`btn_readonly`, active by default), **Preview**
  (`btn_preview`, `document-page-setup` icon, off by default; locks the Read-only
  toggle while active). Separators are `SeparatorToolItem`s with `set_draw(True)`
  (via `_toolbar_separator()`) so the divider line is visible. Card view,
  Read-only, and Preview are marked `set_is_important(True)`: in the "beside"
  toolbar style (`BOTH_HORIZ`) only important items show their label beside the
  icon, so only those three are labelled while New/Save/Refresh/Slugify are
  icon-only; in "below" style (`BOTH`) every item shows its label.
- Note list (pane 2): a vertical box with a **search row** on top (a `Gtk.Entry`
  with a clear icon + a "Search" `Gtk.Button`) above a `Gtk.Stack`
  (`notelist_stack`). The stack has a "list" child (the scrolled
  `Gtk.ListStore(str, str, float, str)` = display name, full path, mtime,
  first-body-line snippet) and a "placeholder" child shown when the Subfolders
  parent is selected. The single cell renderer uses a **cell-data-func**
  (`_note_cell_data`): list view shows the escaped title; card view shows a
  `<b>`-titled block plus the date (`model.format_mtime_value`) and snippet on the
  next two lines, *italicised* and slightly smaller but in the **same colour** as
  the title (so nothing clashes with the selection highlight), and sets the cell's
  `ypad` to 2 for a little extra vertical padding (0 in list view).
  `_apply_card_view()` toggles `set_grid_lines(HORIZONTAL/NONE)` so a thin separator
  line appears between cards only in card view. `_reload_notelist` switches the
  stack back to "list". Search filtering lives in `_reload_notelist`:
  `self.search_query` (None = off) is passed
  to `model.filter_notes`, which matches case-insensitively against each note's name
  **and its full contents**; an empty result sets `self._search_no_results`, which
  `update_status` renders as "No search results found!" instead of the item count.
  The filter persists across node switches and reloads until the box is cleared.
  (Content search reads every candidate file per search — fine for typical note
  collections; for very large trees, consider an index or a background thread — see
  §7.) Beyond filtering the list, `on_search` / `on_search_icon_press` call
  `_apply_search_highlight()`, which tells the active tab to highlight the term (or
  clear it); the current query is also pushed to a
  tab when a note loads into it and on tab switch, so the highlight follows.
- Editor: a `Gtk.Notebook`; each page is an `EditorTab` (see §3.2a). `editor_font`
  themes the whole view; `code_font` themes code spans via the highlighter tags;
  `preview_font` and the two line-spacings theme the preview/editor views. Keep a
  single uniform size for body text — do not introduce size-varying tags.
- Status bar (pane footer): a horizontal box with a bold `mode_label` (Read-only /
  Edit mode, or "Rendered Markdown preview") on the left and the regular
  `Gtk.Statusbar` filling the rest; `update_status` sets both and refreshes the
  Save and Slugify button sensitivities.

## 4. Control flow

- Selecting a sidebar row → `on_sidebar_selection_changed` sets `current_node`
  (and `current_subfolder` for a subfolder), then either reloads the note list
  (All Notes / Empty Notes / a subfolder) or shows the pane-2 + pane-3
  placeholders (the *Subfolders* parent). It does not disturb tab content.
- Searching → `on_search` (Entry "activate"/Enter or the Search button) reads the
  box, sets `search_query`, and reloads; `on_search_icon_press` (the clear icon)
  empties the box and drops the filter. Search runs only on Enter/click, never per
  keystroke.
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
- Toggle read-only → `on_toggle_read_only` → `_apply_read_only` flips editability
  on all tabs and updates the bold status indicator.
- New note → `on_new_note` (blocked with a notice in read-only mode) writes an
  empty file into the selected subfolder, or the root otherwise, via
  `model.create_empty_note`, reloads the list, and opens it in the active tab.
- Slugify → `on_slugify` reads the active tab's live content, derives a slug from
  its H1, **confirms via `_confirm`** (an OK/Cancel `MessageDialog`), then renames
  via `model.rename_note` and refreshes title + list. The button is only sensitive
  in edit mode when those conditions hold (see §3.3 toolbar).
- New tab (Ctrl+T) → `on_new_tab` → `_new_tab(focus=True)`.
- Switch tabs → Ctrl+Tab / Ctrl+Shift+Tab cycle; Alt+1..9 jump (via
  `_on_key_press`).
- Close tab (Ctrl+W / close button) → `on_close_tab` / the tab's close callback →
  `_close_tab`, a no-op at one tab.
- Save → `_save_active` writes the active tab's content to its note.
- Refresh note → `on_refresh_note` reloads the active note from disk (fresh
  `model.Note`), after `_maybe_warn_unsaved` (cancel aborts the reload); re-applies
  the current search highlight and refreshes the status.
- Sort change → `on_sort_changed` reloads the list, keeping the active tab's note
  selected by path.
- Preferences → `on_preferences` opens the dialog and calls `run_modal`; live
  changes preview via `_apply_preferences`, Save persists, Cancel reverts.
- About → `on_about` shows a `Gtk.AboutDialog`.
- Quit / window close → `_confirm_close_all` prompts for each dirty tab.
- Close workspace → `on_close_workspace` (after `_confirm_close_all`) clears the
  sidebar, note list, and tabs, and drops `root_folder`, returning to the empty
  initial state.
- Toggle Toolbar / Statusbar (View menu) → `on_toggle_toolbar` /
  `on_toggle_statusbar` set the visibility of `self.toolbar` / `self.statusbar_box`
  from the `Gtk.CheckMenuItem` state.

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
- The note-list cell uses a **cell-data-func** (`_note_cell_data`) that emits Pango
  markup, so any dynamic text in a card (title, date, first body line) must be
  XML-escaped — it uses `xml.sax.saxutils.escape`. Unescaped `<`/`&` from note
  content would otherwise break rendering. The card sub-lines are italicised and
  share the title's colour (rather than a fixed grey) so they never clash with the
  selection-highlight background.
- Initial keyboard focus is set to the sidebar (`set_focus(self.sidebar_view)`)
  so the first toolbar button doesn't show a focus ring on startup.

## 7. Suggested next features

- Free-form rename note (inline edit in the list; `model.rename_note` already
  exists, so this is mostly UI).
- Delete note (with confirmation; move to trash via `Gio.File.trash`).
- Search performance: content search currently reads every candidate file per
  query. For large note trees, add a content index or run the filter on a
  background thread (and/or debounce) to keep the UI responsive.
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

