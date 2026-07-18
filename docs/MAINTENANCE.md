# MAINTENANCE.md

Technical notes for anyone (human or AI) maintaining `qdvc_markdown_notebook.py`.

This app follows the QDVC common specification; shared conventions (repository
layout, backend dispatch, identity/icon policy, shortcuts, documentation rules,
testing) live there and are **not** duplicated here:
<https://github.com/qdvc-apps/qdvc-python-gtk-app-specification/>. This file
documents what is specific to this app and any deviations (see §5). The
element-by-element GTK3↔GTK4 map is in
[MAINTENANCE_GTK3_GTK4.md](MAINTENANCE_GTK3_GTK4.md).

## 1. Overview

A GTK / PyGObject desktop application with two front-ends on one pure core: a
**GTK 3** front-end (default, MATE/GNOME2-era look) and a parallel **GTK 4 /
libadwaita** front-end (GNOME HIG). No build step, no external Python
dependencies beyond `gi` (PyGObject) and PyYAML. It edits markdown files **in
place** on disk; there is no database, index, or cache.

The code is a thin backend-dispatcher entry point (spec §3) plus the `qdvc`
package: a **GTK-free pure core** (data / application logic + toolkit-independent
UI helpers) and two view sub-packages, `qdvc/gtk3/` (modules prefaced `gtk3_`)
and `qdvc/gtk4/` (prefaced `gtk4_`).

```
qdvc_markdown_notebook.py        # thin dispatcher: --gtk3/--gtk4 → ui_backend → gtk3
qdvc/
    __init__.py                  # APP_ID, APP_NAME, __version__ re-exports
    # ---- GTK-free pure core (no GTK import; unit-testable headless) ----
    config.py                    # constants, sort modes, NODE_* kinds, APP_ID/PRGNAME/icon
    model.py                     # data layer: Note + filesystem + disk I/O + outline parse
    settings.py                  # persistent user settings (YAML) + icon-set/.desktop install
    pango_markdown.py            # Markdown → Pango-markup string renderer (no GTK widget)
    strings.py                   # all user-facing UI text, in one place (for i18n)
    ui_prefs.py                  # shared SHORTCUTS table + toolkit-independent UI helpers
    platform_utils.py            # launch system apps (viewer/editor/file manager)
    highlight_rules.py           # toolkit-independent markdown highlight rules/spans
    # ---- GTK3 view/controller (qdvc/gtk3/, prefaced gtk3_) ----
    gtk3/gtk3_app.py             # NotebookApp: the Gtk.Application (id, icon, prgname)
    gtk3/gtk3_highlighter.py     # MarkdownHighlighter (GTK TextBuffer tagging)
    gtk3/gtk3_editortab.py       # EditorTab: one tab's editor widget + state
    gtk3/gtk3_preferences.py     # PreferencesDialog: the *view* for settings.py
    gtk3/gtk3_menubar.py         # MenuBarMixin: the window's menu bar
    gtk3/gtk3_toolbar.py         # ToolbarMixin: the window's toolbar + styling
    gtk3/gtk3_panes.py           # PanesMixin: the four panes + their data binding
    gtk3/gtk3_actions.py         # ActionsMixin: handlers, context menus, dialogs
    gtk3/gtk3_window.py          # NotebookWindow: composes the mixins (view + controller)
    gtk3/gtk3_shortcuts.py       # wire the shared SHORTCUTS table into GTK3 accels
    # ---- GTK4/libadwaita view (qdvc/gtk4/, prefaced gtk4_) ----
    gtk4/gtk4_app.py             # NotebookApp: the Adw.Application + accels
    gtk4/gtk4_window.py          # NotebookWindow: Adw window, panes, handlers
    gtk4/gtk4_actions.py         # ActionsMixin: win.* Gio.SimpleActions
    gtk4/gtk4_editorview.py      # EditorView: one tab's editor widget + state
    gtk4/gtk4_highlighter.py     # MarkdownHighlighter (reuses highlight_rules)
    gtk4/gtk4_preferences.py     # PreferencesWindow: Adw.PreferencesWindow (live-apply)
    gtk4/gtk4_shortcuts.py       # Gtk.ShortcutsWindow from the shared SHORTCUTS table
```

View modules reach the pure core with `from ..` and siblings with `from .gtk3_x`
/ `from .gtk4_x`. The two view sub-packages never import each other.

1. **The GTK3 layer never touches the filesystem directly.** All disk
   reads/writes/creation go through `model.py` (and `settings.py` for config).
   The core modules import no GTK and are unit-testable without a display.
2. **`settings.py` (model) is paired with `gtk3_preferences.py` (view).** The
   former is *what is stored/loaded*; the latter is *the window for editing it*.
   Naming them as a model/view pair (data vs `gtk3_`) is meant to make that split
   obvious to a newcomer.

`NotebookWindow` itself is assembled from mixins via multiple inheritance
(`class NotebookWindow(MenuBarMixin, ToolbarMixin, PanesMixin, ActionsMixin,
Gtk.ApplicationWindow)`) purely to keep each file readable — it is one class at
runtime, so all methods share `self`. The GTK 4 front-end (now realized in
`qdvc/gtk4/`, selectable via `--gtk4` or the `ui_backend` preference) sits
alongside the `gtk3_` set and reuses the entire GTK-free core.

Run modes:

```bash
python3 qdvc_markdown_notebook.py /path/to/data   # open a folder (GTK3 default)
python3 qdvc_markdown_notebook.py                 # empty; user opens via Ctrl+O
python3 qdvc_markdown_notebook.py --gtk4 [folder] # force the GTK4 front-end
python3 qdvc_markdown_notebook.py --gtk3 [folder] # force the GTK3 front-end
```

The entry point is a thin dispatcher (spec §3): backend = flag → `ui_backend`
config → default `gtk3`. Run from the directory containing both the script and
`qdvc/`.

## 2. Runtime dependencies

- Python 3.10+ (the common spec §4 target; the code uses f-strings and, in the
  highlighter, the walrus `:=`).
- PyGObject and **exactly one** of the two toolkits at runtime:
  - GTK 3 (`python3-gi`, `gir1.2-gtk-3.0`) — the default front-end; or
  - GTK 4 + libadwaita (`gir1.2-gtk-4.0`, `gir1.2-adw-1`) — the modern one.
- `Pango`, `Gdk`, `GLib`, `Gio` come with the GTK introspection data.
- **PyYAML** — used by `settings.py` to persist user settings. If it is missing
  the app still runs with default settings; nothing is saved and a one-line
  warning is printed to stderr. Install with `pip install pyyaml`
  (Debian/MATE: `sudo apt install python3-yaml`).

There is **no** markdown-rendering library (e.g. `markdown`, `mistune`). This is
intentional: the spec requires a monospace view with no font-size variation, so
highlighting is done with regexes against a `Gtk.TextBuffer` and tag table.

## 3. Architecture

The modules group into the **GTK-free core** — `config` (§3.0), `settings`
(§3.0a), `pango_markdown` (§3.1a), `strings` (§3.1b) and `model` (§3.2) — and the
**GTK3 view/controller**, all `gtk3_`-prefixed: `gtk3_highlighter` (§3.1),
`gtk3_editortab` (§3.2a), `gtk3_preferences` (§3.2b) and the `NotebookWindow`
mixins (§3.3). The subsection numbers below are historical labels, not a strict
layer ordering. The core imports no GTK and is unit-testable headless; the GTK3
layer depends on the core but never the reverse.

### 3.0 `config.py` (core)
Plain constants only — `APP_NAME`, `MARKDOWN_EXTENSIONS`, the `SORT_*` mode
strings, the `ALL_NOTES` sentinel, and the sidebar `NODE_*` kind strings
(`NODE_ALL_NOTES`, `NODE_INBOX`, `NODE_EMPTY_NOTES`, `NODE_SUBFOLDERS`,
`NODE_SUBFOLDER`). No
GTK, no I/O, so it is safe to import from anywhere. `ALL_NOTES` is an `object()`;
compare with `is`, never `==`. (`ALL_NOTES` predates the tree sidebar; the sidebar
now uses the `NODE_*` kinds instead.)

### 3.0a `settings.py` — persistent user settings (core; no GTK)
This is the **model** side of preferences (the *view* is `gtk3_preferences.py`,
§3.2b): it defines what is stored and how it is loaded/validated/saved.
- Stores settings as YAML at `$XDG_CONFIG_HOME/qdvc-markdown-notebook/config.yml`,
  falling back to `~/.config/qdvc-markdown-notebook/config.yml`. Resolve via
  `config_dir()` / `config_path()`. Configs written by pre-spec-§5 builds under the
  old `qdvcmdnb` subdirectory are migrated once, on first `load()`, via
  `_migrate_legacy_config()` (`_legacy_config_path()` locates the old file); it is
  best-effort and never raises.
- `Settings` holds `editor_font`, `code_font`, and `preview_font` (Pango
  font-description strings), `editor_line_spacing` and `preview_line_spacing`
  (ints, pixels of extra inter-line space, clamped to `[MIN_LINE_SPACING,
  MAX_LINE_SPACING]` via `_coerce_spacing`), `toolbar_style` (`"below"` or
  `"beside"`, the `TOOLBAR_TEXT_*` constants), `tab_title_length` (int clamped to
  `[MIN_TAB_TITLE_LENGTH, MAX_TAB_TITLE_LENGTH]` via `_coerce_int_range`),
  `remember_sort` and `restore_session` (bools via `_coerce_bool`), `icon_set_dir`
  (a folder path; `""` means the stock icon), `sort_mode` (a persisted `SORT_*`
  string, or `None`), `last_workspace` + `last_open_notes` (the previous session's
  folder and open-note paths, for restore-on-startup), `last_node` +
  `last_subfolder` + `last_selected_note` (the previous sidebar/note-list
  selection, also restored), and `recent_folders` (most-recent-first list, capped
  at `MAX_RECENT`). `editor_font` themes the
  editor; `code_font` themes inline/fenced code in both the editor (highlighter)
  and the preview; `preview_font` is the preview body font; the two spacings apply
  to the editor and preview views. Construct via `Settings.load()`, which returns
  sane defaults on a missing/malformed file or any read error — it never raises to
  the caller. Mutators (`set_*`) validate the same way as `_apply`;
  `set_last_session(workspace, notes, node, subfolder, selected_note)` filters the
  note list to strings and stores the selection fields.
- `icon_set_files(folder)` (module-level, no GTK) validates a custom icon-set
  folder and returns a dict mapping each present pixel size (`ICON_SET_PNG_SIZES`
  = 16, 22, 24, 32, 48, 256) to its `<n>x<n>.png`, plus `"scalable"` →
  `scalable.svg`. Missing files are omitted; a false/non-directory path yields
  `{}`. The window turns this into a window icon list.
- Icon-theme install (module-level, no GTK; all best-effort, never raise):
  `install_icon_set(folder, icon_name=APP_ICON_NAME)` copies the icon-set files
  into `$XDG_DATA_HOME/icons/hicolor/<size>x<size>/apps/<icon_name>.png` (and
  `scalable/apps/<icon_name>.svg`) so external launchers resolve the icon by name;
  `uninstall_icon_set(icon_name)` removes them; `update_desktop_icon(icon_name,
  exec_path=None)` creates or rewrites the per-user `.desktop` file
  (`desktop_file_path()` → `$XDG_DATA_HOME/applications/<DESKTOP_FILE_ID>`),
  changing only its `Icon=` line when the file already exists (other lines
  preserved) and writing a full default entry when it doesn't. `_data_home()`
  resolves `$XDG_DATA_HOME` or `~/.local/share`. `APP_ICON_NAME` =
  `qdvc-markdown-notebook`.
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

### 3.1 `gtk3_highlighter.py` — `MarkdownHighlighter` (GTK3)
- Owns the editor `Gtk.TextBuffer`'s tag table and applies colour/weight tags.
- `_make_tags()` defines tags once (idempotent via `table.lookup`).
- `highlight()` clears all tags over the whole buffer and re-applies them. It is
  **whole-buffer**, called on every `changed` signal. Fine for note-sized files;
  if you need to support very large files, switch to highlighting only the
  changed line range (track via the buffer's `insert-text`/`delete-range`).
- Fenced code blocks (```` ``` ````) are tracked with the `in_fence` toggle as
  lines are scanned in order. Headings are matched first via `_heading_rgx`
  (which captures the leading `#`s), then the other line-level rules
  (blockquotes, lists, hr) and inline rules (inline code, bold, italic, links),
  each a list of `(tag_name, compiled_regex, group)` tuples.
- **Per-level heading colours:** there are six heading tags `heading1`..`heading6`
  in progressively lighter shades of blue (H1 = navy `#204a87`, down to H6
  `#a8c0e2`). `highlight()` counts the `#`s and applies the matching tag, so deeper
  headings read as visually subordinate. (Preview mode uses greys instead — see
  §3.1a.)
- **Italics** are matched in both the `*asterisk*` and `_underscore_` forms (two
  alternatives in one regex). The underscore form is word-bounded (so
  `file_name_here` is not italicised) and neither form matches the doubled
  bold delimiters. Adding the underscore form fixed italics not rendering for
  `_text_`.
- Offsets: the buffer text is split on `\n`; `offset` tracks the character index
  of each line start, `+1` per line for the stripped newline. If you change the
  splitting, keep this accounting correct or tags will land on wrong ranges.
- Code font: the `code_inline` and `code_block` tags no longer hard-code
  `family="monospace"`. `set_code_font(desc)` sets the tags' `font` property
  (a full Pango font-description string, e.g. "Fira Code 10"), so the user's
  *View → Set Code Font* choice fully controls code-span family and size while
  the rest of the editor uses `editor_font`. The constructor takes `code_font`
  and applies it immediately, so already-loaded text reflects the font.

### 3.1a `pango_markdown.py` — Markdown → Pango markup (core; no GTK)
`render(text, code_font=None)` converts a Markdown subset to a Pango markup string
for Preview mode (no WebKit). Pango markup is inline-only (`<b>`, `<i>`, `<tt>`,
`<span>`, size/weight/foreground), so block structure is approximated: headings
become sized+bold spans, lists get bullet/number prefixes with indentation,
blockquotes a `\u2503` bar + italics, fenced/inline code with a grey background,
horizontal rules a line of dashes, links the underlined coloured text (the URL is
dropped — markup can't make clickable links). Heading colours come from
`_HEADING_COLOUR`: black (H1) shading to progressively lighter greys (H2–H6) —
distinct from the editor's blues (`#000000`, `#2e2e2e`, `#555555`, `#777777`,
`#999999`, `#b0b0b0`). When `code_font` (a Pango
font-description string) is supplied, code spans/blocks use it via
`<span font_desc=...>`; otherwise they fall back to `<tt>` (generic monospace).
Attribute values are quote-escaped (`_attr_escape`) so a font name with an
apostrophe can't break the markup. All text is XML-escaped first, and code is
escaped but not further interpreted. The output is always well-formed markup. Pure
text→text, no GTK, so it is unit-testable. Deliberately lightweight (same "good
enough" philosophy as the highlighter), not a full CommonMark parser.

### 3.1b `strings.py` — UI text catalogue (core; no GTK)
Every user-facing string the GTK layer displays lives here, so a future
translation pass has a single file to work from. Strings are grouped under small
namespace classes — `Menu`, `Toolbar`, `Sidebar`, `Editor`, `Status`, `Prefs`,
`Dialog` (never instantiated, just used as `Menu.FILE` etc.). Strings that embed
runtime values are exposed as functions (e.g. `status_items(count, selected)`,
`Dialog.confirm_move_body(name, dest)`, `Dialog.err_open(path)`) so the
`.format`/f-string — and therefore the word order — stays in this file where a
translator controls it, not at the call site. `APP_NAME` keeps living in
`config.py` (it doubles as the WM/program identity) and is re-exported here as a
convenience. Two purely presentational literals are intentionally **not**
centralised: the title-truncation ellipsis and the em-dash in the window title
(punctuation, not translatable phrases). Migration path to gettext: wrap the
literals in `_()` and install a translation domain; call sites are unaffected
because they already reference these names. The `gtk3_` modules each
`from .strings import <Namespace>` and use the constants/functions.

### 3.2 `model.py` — data layer (core; no GTK)
- `Note` — a thin wrapper over a file path; caches `name` and `mtime`.
  `display_name()` strips a known markdown extension for the list label.
- `is_markdown(filename)` — extension check against `MARKDOWN_EXTENSIONS`.
- `collect_notes(folder)` — recursive `os.walk`; returns all markdown files at
  **any** depth. This is how both "All Notes" and the per-subfolder view get
  their contents, which implements the spec's "aggregate deeper levels to the
  parent subfolder" rule: selecting a top-level subfolder shows everything under
  it recursively.
- `collect_top_level_notes(folder)` — markdown files **directly** inside `folder`
  only (no recursion). Backs the sidebar's *Inbox* node (notes not yet filed into
  a subfolder).
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
- `move_note(note, dest_folder)` moves a note into another folder, keeping its
  filename (collision-avoided via `unique_note_path`), updating the `Note` in
  place; a no-op when it already lives there, raises `OSError` if the destination
  is not a directory. `all_subfolders(root)` returns every subfolder under `root`
  at any depth as paths relative to `root`, sorted, with `""` first (the top
  level); hidden dirs (and their descendants) are pruned. These back the pane-2 /
  tab **Move to subfolder** submenu.
- `parse_headings(text)` — parses ATX headings (`#`..`######`) for the outline
  pane, returning a list of `{"level", "title", "line"}` dicts (0-based line
  index). Fenced code blocks (` ``` ` or `~~~`) are skipped so a `#` inside code
  isn't mistaken for a heading; closing ATX `#`s are stripped from the title; a
  `#` with no following space is not a heading. Pure text→list, no GTK, testable.

### 3.2a `gtk3_editortab.py` — `EditorTab` (GTK3)
Encapsulates one tab's editor state, which previously lived directly on the
window. Each `EditorTab` owns its own `Gtk.TextView`, `Gtk.TextBuffer`,
`MarkdownHighlighter`, the `note` open in it (or `None`), per-tab `dirty` /
`_loading` flags, and its own **`read_only`** and **`preview`** view state
(read-only and preview are per-tab; see §3.3). `set_read_only(on)` flips the
`TextView` editability and the tab-label padlock icon; `set_preview(on)` switches
the stack child and the tab-label preview icon. `set_editable` is the low-level
helper `set_read_only` calls.
- `widget` — the page widget added to the `Gtk.Notebook`. It is a `Gtk.Stack`
  with three named children: `"editor"` (a scrolled `TextView`), `"preview"` (a
  read-only `TextView` showing rendered markdown), and `"placeholder"` (a centred
  dim "Select a note…" message). `_update_view_mode()` picks the child: placeholder
  when `note is None`, else `"preview"` when `self.preview`, else `"editor"`. It is
  called from `clear()`, `load_note()`, and `set_preview()`. A fresh Ctrl+T tab
  shows the placeholder until a note is loaded.
- `tab_label` — a horizontal box with 2px margins on all sides, holding: two
  mode-indicator icons at the **start** (a read-only padlock
  `changes-prevent-symbolic` and a preview `document-page-setup` icon, each at
  `MENU` = 16px size, created with `set_no_show_all(True)` so only
  `_refresh_status_icons()` controls their visibility — both can show at once),
  then an `EventBox`-wrapped title label, then a borderless close button
  (Caja-style, `window-close` icon at `MENU` size). The EventBox (with
  `visible_window=False`) lets the title receive a right-click, which fires the
  `on_context_menu(tab, event)` callback (the window shows the tab context menu;
  no-op when the tab has no note). The title is the note's display name, truncated
  to `_tab_title_length` characters (default `MAX_TAB_TITLE` = 12, overridable per
  tab and set from `settings.tab_title_length`) with a trailing ellipsis when
  longer; a leading `*` marks unsaved changes. Truncation is done in
  `_refresh_title()` on the string itself (not via Pango width-ellipsize, which
  depended on allocated width and could clip even short names).
  `set_tab_title_length(n)` updates the budget and refreshes.
- A `key-press-event` handler on the editor `TextView`
  (`_on_textview_key_press`) converts a plain **Tab** keypress into `TAB_SPACES`
  (4) spaces while the view is editable, swallowing the event so focus doesn't
  jump out; Shift+Tab and read-only mode fall through to the default handler.
- Callbacks passed in by the window: `on_changed(tab)` (buffer edited, not during
  a programmatic load), `on_close(tab)` (close button clicked), and
  `on_context_menu(tab, event)` (right-click on the tab label).
- API: `load_note(note)` → bool, `save()` → bool (both return False on I/O error
  and leave the dialog to the caller), `clear()`, `get_content()`,
  `apply_font(str)`, `apply_code_font(str)` (also re-renders the preview if
  active), `apply_preview_font(str)` (preview body font), `apply_editor_line_spacing(px)`
  / `apply_preview_line_spacing(px)` (set `pixels_below_lines` + `pixels_inside_wrap`
  on the editor/preview views), `set_editable(bool)` (read-only mode; toggles
  `TextView.set_editable`/`set_cursor_visible`), `set_preview(bool)` (renders
  current content via `pango_markdown.render(..., code_font=self._code_font)` into
  the preview buffer with `insert_markup`, then switches the stack),
  `highlight_search(query)` (see below), `title_text()`,
  `scroll_to_line(line_index)` (clamp the cursor to a 0-based source line and
  scroll it into view — used by the outline pane to jump to a heading; grabs
  editor focus unless in preview). The constructor takes
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

### 3.2b `gtk3_preferences.py` — `PreferencesDialog` (GTK3)
The **view** for the settings model (§3.0a): the dialog that lets the user edit
what `settings.py` stores. A modal `Gtk.Dialog` (GNOME2/MATE idiom: "Preferences" under the **Edit** menu)
with a `Gtk.Notebook` of two tabs. **Fonts**: `Gtk.FontButton`s for editor font,
code font, and markdown-preview font, plus two `Gtk.SpinButton`s for editor and
preview line spacing (range `MIN_LINE_SPACING`..`MAX_LINE_SPACING`). **Interface**:
a radio pair for toolbar text below vs beside icons; a `Gtk.SpinButton` for the
tab-title length (`MIN_TAB_TITLE_LENGTH`..`MAX_TAB_TITLE_LENGTH`); two
`Gtk.CheckButton`s for *remember sort order* and *restore session*; and a
`Gtk.FileChooserButton` (+ a Clear button) for the custom icon-set folder. It has
**Save** and **Cancel** buttons. Each control change applies **live** (mutates the
shared `Settings` in memory and calls the window's `on_apply` to re-theme), but is
*not* persisted until Save. The dialog snapshots all original values on open
(`_original`, now ten fields); `run_modal()` runs the dialog and, on Save, calls
`settings.save()`, while on Cancel/close it restores the snapshot and re-applies
(reverting the live preview). The window calls `dialog.run_modal()` rather than
just constructing it.

### 3.3 `gtk3_window.py` + mixins — `NotebookWindow` (GTK3 view + controller)
`NotebookWindow` is composed from mixins via multiple inheritance to keep each
file readable — at runtime it is a single class, so every method shares `self`
and there is no behavioural difference from the former monolithic `window.py`:

```
class NotebookWindow(MenuBarMixin, ToolbarMixin, PanesMixin, ActionsMixin,
                     Gtk.Window): ...
```

- `gtk3_window.py` — the core: `__init__`, `_build_ui` (assembles the panes),
  icon-set install + session restore, the live font/spacing appliers, the
  view-toggle state machine (read-only / preview / card view / outline) with its
  menu↔toolbar sync, tab management, the status bar, `open_folder`, and the
  recent-workspace menu.
- `gtk3_menubar.py` (`MenuBarMixin`) — `_build_menubar`, `_icon_menu_item`,
  `_resolve_icon_name`.
- `gtk3_toolbar.py` (`ToolbarMixin`) — `_build_toolbar`, `_toolbar_separator`,
  `_toolbar_style_enum`, `_apply_toolbar_style`.
- `gtk3_panes.py` (`PanesMixin`) — `_build_sidebar` / `_build_notelist` /
  `_build_editor` / `_build_outline` / `_build_statusbar` and the reload /
  cell-render / selection / outline-refresh helpers that bind panes 1, 2 and 4 to
  `model`.
- `gtk3_actions.py` (`ActionsMixin`) — the `on_*` handlers, the right-click and
  tab context menus, move/locate, search, workspace open/close/refresh,
  preferences/about, session save, and the shared confirm/error dialogs.

When adding a method, put it in the mixin that owns its concern; avoid defining
the same method name in two mixins (the MRO would silently shadow one). The order
of mixins in the class statement is the MRO order, but since names don't collide
it doesn't matter in practice.

The editor area is a `Gtk.Notebook` of `EditorTab` pages; `self._tabs` is a
list kept parallel to the notebook pages. Most editor operations delegate to the
**active tab** via `_active_tab()`.

On startup the window centers itself (`set_position(CENTER)`) and sets its icon
name to `accessories-text-editor`; the entry point also calls
`Gtk.Window.set_default_icon_name(...)` and `GLib.set_prgname(...)` so the
panel/taskbar can match the window to the `.desktop` file (its `StartupWMClass`).
`_apply_icon_set()` then overrides the icon when `settings.icon_set_dir` resolves
(via `icon_set_files`) to a usable set. It does three things: (1) loads the SVG +
PNGs as `GdkPixbuf.Pixbuf`es and calls `set_icon_list` +
`Gtk.Window.set_default_icon_list` for an immediate in-process icon; (2) installs
the files into the user's hicolor theme via `install_icon_set(...)` under
`APP_ICON_NAME` and rewrites the per-user `.desktop` file's `Icon=` line via
`update_desktop_icon(APP_ICON_NAME, exec_path=self._script_path())` so external
launchers resolve it; (3) refreshes the running theme with
`_refresh_icon_theme()` (`Gtk.IconTheme.get_default().rescan_if_needed()`). When
no/invalid set is configured it reverts everything to the stock
`accessories-text-editor` (`uninstall_icon_set` + desktop Icon= reset). All steps
are best-effort and fall back to the stock icon. `_script_path()` returns the
absolute entry-point path for the `.desktop` Exec line. `sort_mode` is seeded from
`settings.sort_mode` when `remember_sort` is on, and the matching View-menu radio
(`self._sort_items`) is activated after the menu is built. When no folder is given
on the CLI and `restore_session` is on, `_restore_last_session()` reopens
`last_workspace`, restores the pane-1 sidebar selection (`last_node` /
`last_subfolder`, via `_select_sidebar_node`, which reloads pane 2), loads each
still-existing `last_open_notes` path (first into the initial tab, the rest into
new tabs), and restores the pane-2 note selection (`last_selected_note`).

Menu items use `_icon_menu_item(label, icon_name)`, which builds a
`Gtk.ImageMenuItem` (deprecated in GTK3 but the idiomatic MATE-era way to show
icons in menus; it falls back to a plain `MenuItem`) and calls
`set_always_show_image(True)` so the icon renders even when the desktop's global
`gtk-menu-images` setting is off. The icon name is first passed through
`_resolve_icon_name(icon_name)`, which returns it when the current
`Gtk.IconTheme` has it, else a per-name fallback from `_ICON_FALLBACKS` (e.g.
`help-about` → `dialog-information`) when the theme has that, so a missing themed
icon never leaves a broken slot (spec §8). Icons are stock freedesktop
names: New note=`document-new`, Save note=`document-save`, Refresh
note=`view-refresh`, Open workspace=`folder-open`, Refresh
workspace=`view-refresh`, Open recent workspace=`document-open-recent`, New
tab=`tab-new`, Quit=`application-exit`, Preferences=`preferences-system`,
About=`help-about`. The four View-menu mode toggles (Read-only, Card view,
Preview, Headings outline) are `Gtk.CheckMenuItem`s that mirror the toolbar's
toggle buttons (see below); plain items (Close workspace, Close tab, the
Toolbar/Statusbar toggles, and the sort radio items) intentionally have no icon,
per HIG restraint.

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
- `read_only` / `preview_mode` — **mirrors** of the active tab's per-tab
  read-only / preview state (each `EditorTab` is the source of truth). Kept
  current by the toggles and by `_sync_view_toggles_to_tab` on tab switch.
- `_custom_title` — a session-only user-set window title (`None` = default;
  see `_update_window_title`).
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
  File). Right-click in the note list → `on_notelist_button_press` and right-click
  on a tab label → `_on_tab_context_menu` both build a popup via the shared
  `_build_note_context_menu(note_path, include_locate, tab)`: **Open in new tab**,
  **Move to subfolder** (a submenu from `_build_move_submenu`), **Copy full path**,
  **Show in file browser**, several with icons. The tab variant passes
  `include_locate=True`, prepending **Locate in subfolders** (`_locate_note_in_panes`).
  A pane-2 right-click reads the row under the pointer but **does not change the
  selection** (the handler returns `True` to suppress GTK's default select), so
  right-clicking a note never opens it in the active tab. Move/locate are detailed
  under control flow below.
- Quitting/closing the window runs `_confirm_close_all`, which prompts for *every*
  dirty tab before exit.

Read-only and preview are **per-tab** (each `EditorTab` owns its own `read_only`
and `preview` flags). The toolbar/menu toggles act on, and reflect, the **active
tab** only; `self.read_only` / `self.preview_mode` on the window are *mirrors* of
the active tab's state, kept current so the status bar and Slugify gating can read
them cheaply. New tabs start at the app defaults (read-only on, preview off),
independent of the other tabs.

Read-only mode (toolbar toggle, default on per tab): `_apply_read_only()` calls
`tab.set_read_only(...)` on the **active** tab (which flips the `TextView`'s
editability and shows/hides the tab-label padlock icon) and refreshes the status
bar. Edit actions are gated on the mirror: New note shows a notice and aborts, and
Slugify is desensitised in `_update_slugify_sensitivity`. Saving is left allowed
(a read-only buffer cannot have changed, so it is harmless).

Preview mode (toolbar toggle, default off per tab): `_apply_preview()` calls
`tab.set_preview(...)` on the **active** tab, **disables the Read-only toggle**
(both the toolbar button and the menu item) so it can't be changed while
previewing, refreshes the status bar, and refreshes the outline.
In `update_status` the bold mode label shows "Rendered Markdown preview" when the
active tab is previewing, overriding the read-only/edit label; otherwise it shows
"Read-only mode" / "Edit mode". Preview is always read-only by construction (the
preview `TextView` is non-editable), independent of the tab's `read_only` flag.

On tab switch, `on_tab_switched` calls `_sync_view_toggles_to_tab(tab)`, which
copies the switched-to tab's `read_only`/`preview` onto the window mirrors, sets
both toggle widgets to match via `_sync_toggle` (guarded so the handlers don't
re-fire), and re-locks the Read-only toggle if that tab is previewing. The
tab-label shows a 16×16 padlock icon while read-only and the preview icon while
previewing (both can show at once); the tab label also carries 2px of extra
padding on every side.

Mode-toggle menu↔toolbar sync: each of Read-only, Card view, Preview, and the
Headings outline exists **both** as a toolbar `Gtk.ToggleToolButton` (`btn_*`) and
a View-menu `Gtk.CheckMenuItem` (`mi_*`). Each has a single entry point —
`_set_read_only` / `_set_card_view` / `_set_preview` / `_set_outline` — that
updates the (active-tab or window) state, calls `_sync_toggle(button, menu_item,
value)` to set both widgets without re-firing (guarded by
`self._syncing_view_toggles`), then applies the effect. The toolbar handlers
(`on_toggle_*`) and menu handlers (`on_menu_toggle_*`) both early-return when the
guard is set and otherwise funnel into the matching `_set_*`. (Card view and the
outline remain window-wide; only Read-only and Preview are per-tab.) Shortcuts:
Read-only Ctrl+E, Card view Ctrl+D, Preview Ctrl+\` , Outline Ctrl+Shift+O.

Headings outline (pane 4, toggle default off): `_build_outline()` builds a
`Gtk.ScrolledWindow` (`outline_scroll`, `set_no_show_all(True)` so it stays hidden)
containing `outline_view`, a `Gtk.TreeView` over `outline_store`
(`Gtk.TreeStore(str, int)` = label, 0-based source line). It sits in a third
nested `Gtk.Paned` (`_editor_split`: editor | outline). `_apply_outline_visibility`
shows/hides the scroll and, when shown, calls `_refresh_outline()`, which clears
the store and rebuilds it from `model.parse_headings(active_tab.get_content())`,
nesting rows by heading level using a `(level, iter)` stack, then `expand_all()`.
It is refreshed on note load, tab switch, buffer change, and preview toggle.
`_refresh_outline(tab=None)` defaults to the active tab, but `on_tab_switched`
passes the switched-to tab explicitly: GTK's `switch-page` fires *before* the
notebook updates its current-page index, so `_active_tab()` would still return
the previously-viewed tab there (this was a real bug — the outline showed the
prior note's headings after a switch).
Clicking a row (`row-activated`) or selecting it (`changed`, guarded by
`_outline_guard`) calls `_jump_to_outline_line` → `tab.scroll_to_line(line)`.

Refresh workspace (`on_refresh_workspace`, File menu, Ctrl+Shift+R): re-scans the
working folder and rebuilds panes 1+2 from disk via
`_reload_sidebar(preserve_selection=True)` (which remembers the current node /
subfolder and re-selects it after rebuild, falling back to All Notes) then
`_reload_notelist(select_path=...)` to keep the pane-2 selection. Open tabs are
untouched. `_select_sidebar_node(kind, subfolder)` now returns a bool indicating
whether a matching row was found.

Inbox node (`NODE_INBOX`): a sidebar row between All Notes and Empty Notes
(`mail-inbox` icon) that lists `model.collect_top_level_notes(root_folder)` — the
top-level (non-recursive) markdown files. `_notes_for_current_subfolder` handles
it; `on_sidebar_selection_changed` treats it like the other note-listing nodes.

Menus (order **File, Edit, View, Help**): **File** (New note, Save note, Refresh
note, | Open workspace, Refresh workspace, Close workspace, Open recent workspace,
| New tab, Close tab, | Quit), **Edit** (Preferences, Set window title\u2026),
  **View** (Toolbar and
Statusbar `Gtk.CheckMenuItem` toggles, a separator, the Read-only/Card view/
Preview/Headings outline mode toggles, a separator, then the three sort
`RadioMenuItem`s), **Help** (About). Refresh note (`mi_refresh`, Ctrl+R) mirrors
the toolbar button and is sensitivity-synced in `_update_save_sensitivity`;
Refresh workspace (`mi_refresh_ws`, Ctrl+Shift+R) uses the same `view-refresh`
icon. `on_close_workspace` resets to the empty
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
font, code font, preview font, line spacings, toolbar style, **tab-title length**
(`_apply_tab_title_length` → `tab.set_tab_title_length` on every tab), and the
**icon set** (`_apply_icon_set`) to the live UI. `_apply_editor_font` /
`_apply_code_font` / `_apply_preview_font` / `_apply_line_spacing` /
`_apply_tab_title_length` iterate **all** tabs; `_apply_toolbar_style` maps
`settings.toolbar_style` to a `Gtk.ToolbarStyle` (`BOTH` = below, `BOTH_HORIZ` =
beside) via `_toolbar_style_enum()`. `on_open_recent` opens a folder from the menu
(handling the case where it has since been deleted). On quit / window close,
`_save_session()` records `root_folder`, the open notes' paths, **and** the
current sidebar node / subfolder / pane-2 note selection into settings and saves
(so toggling *restore session* later just works); `on_sort_changed` persists
the new `sort_mode` when *remember sort order* is on.

Note: inside the selection handlers the local variable for the GTK model is
named `model_` (trailing underscore) to avoid shadowing the imported `model`
module.

UI is built in `_build_*` methods and assembled in `_build_ui()`:
- Layout: `vbox` → menubar, toolbar, then nested `Gtk.Paned`. `outer`
  (horizontal) holds sidebar + `inner`; `inner` holds the note list +
  `editor_split`; `editor_split` (`self._editor_split`) holds the editor notebook
  + the outline pane (pane 4). Then the statusbar. Pane positions set with
  `set_position`; the outline pane is hidden until toggled (`set_no_show_all`).
- Sidebar: `Gtk.TreeStore(str, str, str, str)` = (icon-name, label, node-kind,
  subfolder-name). A `CellRendererPixbuf` (icon-name → column 0) precedes the text
  renderer (label → column 1). Built by `_reload_sidebar` as a **tree**: top-level
  rows for *All Notes* (`emblem-documents`), *Inbox* (`mail-inbox`, `NODE_INBOX`,
  top-level notes only), *Empty Notes* (`edit-clear`), and *Subfolders* (`folder`);
  each immediate subfolder is a child of the Subfolders
  row (`NODE_SUBFOLDER`, label and column-3 = its name). `expand_all()` keeps the
  branch open. `_reload_sidebar(preserve_selection=True)` re-selects the prior
  node/subfolder after a rebuild (used by Refresh workspace), else it selects All
  Notes. `on_sidebar_selection_changed` switches on the node kind (column 2):
  All/Inbox/Empty/subfolder reload the list; the Subfolders **parent** shows
  placeholders in both panes (`_show_notelist_placeholder` + `tab.clear()`).
- Toolbar: built in `_build_toolbar`, style from `_toolbar_style_enum()`. Order:
  **New tab** (`tab-new`; first item, opens an empty tab via `on_new_tab`),
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
  toggle while active), **Outline** (`btn_outline`, `view-list` icon, off by
  default — shows/hides pane 4), `|` separator, **Window title** (`btn_set_title`,
  `document-properties`; `on_set_window_title` prompts for a custom window title).
  Separators are `SeparatorToolItem`s with
  `set_draw(True)` (via `_toolbar_separator()`) so the divider line is visible.
  Card view, Read-only, Preview, and Outline are marked `set_is_important(True)`:
  in the "beside" toolbar style (`BOTH_HORIZ`) only important items show their
  label beside the icon, so only those are labelled while
  New-tab/New/Save/Refresh/Slugify/Window-title are icon-only; in "below" style
  (`BOTH`) every item shows its label. Each of Read-only/Card view/Preview/Outline
  has a matching View-menu `Gtk.CheckMenuItem` kept in sync (see the toggle-sync
  paragraph above).
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
- Outline (pane 4): `_build_outline` → `outline_scroll` (hidden via
  `set_no_show_all`) wrapping `outline_view` over `outline_store`
  (`Gtk.TreeStore(str, int)` = label, source line). Rebuilt by `_refresh_outline`
  from `model.parse_headings`, nested by heading level; clicking/selecting a row
  jumps the active tab to that line. See the Headings-outline paragraph above.
- Status bar (pane footer): a horizontal box with a bold `mode_label` (Read-only /
  Edit mode, or "Rendered Markdown preview") on the left and the regular
  `Gtk.Statusbar` filling the rest; `update_status` sets both and refreshes the
  Save and Slugify button sensitivities.

## 4. Control flow

- Selecting a sidebar row → `on_sidebar_selection_changed` sets `current_node`
  (and `current_subfolder` for a subfolder), then either reloads the note list
  (All Notes / Inbox / Empty Notes / a subfolder) or shows the pane-2 + pane-3
  placeholders (the *Subfolders* parent). It does not disturb tab content.
- Searching → `on_search` (Entry "activate"/Enter or the Search button) reads the
  box, sets `search_query`, and reloads; `on_search_icon_press` (the clear icon)
  empties the box and drops the filter. Search runs only on Enter/click, never per
  keystroke.
- Selecting a note (single click) → `on_note_selection_changed` checks the active
  tab for unsaved changes (cancelling restores the prior selection via
  `_reselect_active_note`), then `_load_note_in_active_tab` **replaces** the
  active tab's content.
- Right-click a note (pane 2) or a tab label → a shared popup
  (`_build_note_context_menu`): "Open in new tab" (`_load_note_in_new_tab`),
  "Move to subfolder" (a submenu of `model.all_subfolders`; `_move_note_to`
  confirms via `_confirm` then calls `model.move_note`. It locates every open tab
  on the note **by old path**, repoints each to the new path and refreshes the
  title (no disk reload — a move doesn't change content, and this avoids reading
  the now-gone old path), then rebuilds the sidebar and re-selects the note in
  pane 2 with `_note_select_guard` set so the reselection doesn't re-trigger a
  tab reload), "Copy full path"
  (`_copy_path_to_clipboard` via the `CLIPBOARD` selection), and "Show in file
  browser" (`_show_in_file_browser`, which converts the parent dir to a `file://`
  URI with `GLib.filename_to_uri` and opens it via `Gtk.show_uri_on_window`). The
  tab variant adds "Locate in subfolders" (`_locate_note_in_panes`): it finds the
  immediate subfolder containing the note (or All Notes for a root-level note),
  selects that sidebar row via `_select_sidebar_node` (which reloads pane 2), then
  selects the note's row.
- Tab key in the editor → handled in `EditorTab._on_textview_key_press` (inserts
  four spaces in edit mode; not a window-level concern).
- Typing → the tab's own `_buffer_changed` sets its `dirty` flag, re-highlights,
  updates the tab title, and calls back to the window (`_on_tab_changed` →
  `update_status`, which also re-evaluates Slugify sensitivity).
- Toggle read-only / card view / preview / outline → from either the toolbar
  button (`on_toggle_*`) or the View-menu item (`on_menu_toggle_*`) into the
  single `_set_*` entry point, which syncs both widgets (`_sync_toggle`, guarded)
  and applies the effect. Read-only and preview act on the **active tab** only
  (per-tab state) and update that tab's label icon; card view and outline are
  window-wide (outline shows/hides pane 4 and rebuilds it).
- New note → `on_new_note` (blocked with a notice when the active tab is
  read-only) writes an empty file into the selected subfolder, or the root
  otherwise, via `model.create_empty_note`, reloads the list, and opens it in the
  active tab.
- Slugify → `on_slugify` reads the active tab's live content, derives a slug from
  its H1, **confirms via `_confirm`** (an OK/Cancel `MessageDialog`), then renames
  via `model.rename_note` and refreshes title + list. The button is only sensitive
  in edit mode when those conditions hold (see §3.3 toolbar).
- New tab (Ctrl+T, or the first toolbar button) → `on_new_tab` →
  `_new_tab(focus=True)`. New tabs start read-only / not previewing.
- Switch tabs → Ctrl+Tab / Ctrl+Shift+Tab cycle; Alt+1..9 jump (via
  `_on_key_press`). On switch, `on_tab_switched` syncs the Read-only/Preview
  toggles to the new tab (`_sync_view_toggles_to_tab`), updates panes 1+2 to the
  new tab's note (`_sync_panes_to_tab`, guarded so it doesn't reopen), and
  refreshes the outline for the new active tab.
- Set window title → `on_set_window_title` (Edit menu / toolbar) prompts with an
  entry; OK applies a custom session-only title, Reset clears back to the
  default, Cancel does nothing. `_update_window_title` derives the actual title
  (custom › "app — folder" › "app").
- Close tab (Ctrl+W / close button) → `on_close_tab` / the tab's close callback →
  `_close_tab`, a no-op at one tab.
- Save → `_save_active` writes the active tab's content to its note.
- Refresh note → `on_refresh_note` reloads the active note from disk (fresh
  `model.Note`), after `_maybe_warn_unsaved` (cancel aborts the reload); re-applies
  the current search highlight and refreshes the status.
- Refresh workspace (Ctrl+Shift+R) → `on_refresh_workspace` re-scans the working
  folder and rebuilds panes 1+2 (`_reload_sidebar(preserve_selection=True)` +
  `_reload_notelist`), keeping the selection; tabs untouched.
- Outline navigation → clicking/selecting an outline row calls
  `_jump_to_outline_line` → `EditorTab.scroll_to_line`; the outline rebuilds on
  note load, edit, tab switch, and preview toggle.
- Sort change → `on_sort_changed` reloads the list, keeping the active tab's note
  selected by path, and persists `sort_mode` when *remember sort order* is on.
- Preferences → `on_preferences` opens the dialog and calls `run_modal`; live
  changes preview via `_apply_preferences`, Save persists, Cancel reverts.
- About → `on_about` shows a `Gtk.AboutDialog`; `_set_about_logo` gives it the
  custom icon set's image (SVG or largest PNG at 64px) when one is configured,
  falling back to the installed themed name (`APP_ICON_NAME`) or the stock
  `accessories-text-editor`.
- Quit / window close → `_confirm_close_all` prompts for each dirty tab, then
  `_save_session()` records the workspace, open notes, and the sidebar/note-list
  selection for restore.
- Startup restore → when no CLI folder is given and *restore session* is on,
  `_restore_last_session()` reopens the last workspace, restores the pane-1 and
  pane-2 selections, and reopens its notes.
- Close workspace → `on_close_workspace` (after `_confirm_close_all`) clears the
  sidebar, note list, and tabs, and drops `root_folder`, returning to the empty
  initial state.
- Toggle Toolbar / Statusbar (View menu) → `on_toggle_toolbar` /
  `on_toggle_statusbar` set the visibility of `self.toolbar` / `self.statusbar_box`
  from the `Gtk.CheckMenuItem` state.

## 5. Deviations from the common spec

Stated explicitly with rationale, per the spec's §12 requirement. The spec URL
is in the header above.

- **Quit shortcut.** The family default is `Ctrl+Q` (spec §10), which is what
  the app uses. (An older, app-internal spec draft listed `Ctrl+S` for Quit,
  colliding with Save; that is intentionally not followed.)
- **Rename.** There is no free-form rename UI; renaming happens via **Slugify**,
  which derives the filename from the note's H1. New notes start as `Untitled.md`,
  `Untitled 1.md`, … A general inline-rename (spec default `F2`) remains a
  natural next feature (§7).
- **`Adw.TabView` for editor tabs (GTK 4).** Spec §9 names `Adw.ViewStack` +
  `Adw.ViewSwitcher` for a *multi-view* app. This app's tabs are **documents**,
  not top-level app views, so the HIG-correct widget is `Adw.TabView` /
  `Adw.TabBar`; `ViewStack` is for switching app modes, which this app has none
  of. See MAINTENANCE_GTK3_GTK4.md §4.
- **`settings.py` config API shape.** Spec §5 describes a thin `get(key,
  default)` / `set(key, value)` wrapper over a `DEFAULTS` dict. This app instead
  uses a typed `Settings` class with per-field validated accessors and a
  `SCHEMA_VERSION`; unknown keys are preserved via `_extra` for the same
  no-migration-on-new-key robustness the spec seeks. Retained because it predates
  the shared spec and the validation is valuable; the outcome (YAML at the XDG
  path, forward-compatible) matches the spec's intent.
- **Config subdirectory migration.** The canonical path is
  `~/.config/qdvc-markdown-notebook/config.yml` (spec §5). Configs written by
  pre-spec builds under the old `qdvcmdnb` subdirectory are migrated once on first
  load (`_migrate_legacy_config`).
- **Desktop integration.** The app ships no installer; the base `.desktop` file
  is set up by hand (see README). Choosing a custom icon set in Preferences makes
  the app install icons into the user's hicolor theme and **rewrite the per-user
  `.desktop` file's `Icon=` line** itself (`update_desktop_icon`), so a
  hand-edited `Icon=` line may be overwritten on the next icon-set change.
- **Not yet present.** No `validate()` on the model (spec §6, a SHOULD — the flat
  markdown workspace has little to validate); no `Gtk.Calendar` date entry (spec
  §8.2 — the app has no date-entry fields).

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
- `NotebookWindow` is split across `gtk3_window.py` + four mixin files. They are
  **one class** at runtime. Don't define a method name in two mixins (the MRO
  silently keeps one). A method may freely call another defined in a different
  mixin — they all resolve on `self`. Keep new methods in the mixin matching their
  concern (menu/toolbar/panes/actions) or in the window core for lifecycle/state.
- **New user-facing text goes in `strings.py`, not inline.** Add a constant to
  the right namespace (or a function if it interpolates values) and reference it
  from the `gtk3_` code. The two deliberate exceptions are pure punctuation (the
  truncation ellipsis and the window-title em-dash). Icon names, Pango markup
  tags, and `config.SORT_*`/`NODE_*` identifiers are not UI text and stay put.
- **`Gtk.Notebook` "switch-page" fires before the page index updates.** Inside
  `on_tab_switched`, use the `page_num` argument GTK hands you, not
  `get_current_page()`/`_active_tab()` — those still report the *old* tab at that
  moment. (This bit the outline once: it showed the previous note's headings on
  switch. `_refresh_outline` now takes the switched-to tab explicitly.)

## 7. Suggested next features

- Free-form rename note (inline edit in the list; `model.rename_note` already
  exists, so this is mostly UI).
- Delete note (with confirmation; move to trash via `Gio.File.trash`).
- Search performance: content search currently reads every candidate file per
  query. For large note trees, add a content index or run the filter on a
  background thread (and/or debounce) to keep the UI responsive.
- File-system watch (`Gio.FileMonitor`) to auto-refresh on external changes — a
  natural automatic companion to the manual Refresh workspace command.
- Per-note word/char count in the status bar.
- Export the rendered preview to HTML (reuse `pango_markdown` or add a real
  Markdown→HTML pass).
- Pinned/favourite notes (another sidebar node, like Inbox).
- Remember window geometry (e.g. as more keys in the settings YAML). The last
  folder, open notes, and pane selections are now restored via `restore_session`;
  geometry is not.
- Outline could highlight the heading nearest the cursor as you scroll/edit
  (currently it only jumps on click).
- Experimental **GTK4 view** alongside the GTK3 one. The core modules (`config`,
  `model`, `settings`, `pango_markdown`, `strings`) are already GTK-free, so a
  parallel `gtk4_*` module set could be written against them and selected at
  launch (e.g. a `ui_toolkit` setting in `config.yml`, surfaced in Preferences).
  The entry point would import `gtk4_window` vs `gtk3_window` based on that
  setting. A GTK4 view would reuse `strings.py` verbatim.
- **Translations (i18n).** `strings.py` already centralises every UI string. To
  ship translations, wrap each literal in a gettext `_()` and install a domain
  (`gettext.translation(...).install()` in the entry point), then provide `.po`
  files. Call sites need no change since they reference the `strings` names.

## 8. Testing

There is no formal test suite yet, but the refactor makes the model layer
testable without a display, since the core modules (`config.py`, `model.py`,
`settings.py`, `pango_markdown.py`, `strings.py`) import no GTK. The GTK3 view modules
(`gtk3_*.py`) need GTK to import, but can be sanity-checked for composition (that
`NotebookWindow` resolves all its mixin methods) with a stubbed `gi`.

Syntax-check everything:

```bash
python3 -m py_compile qdvc_markdown_notebook.py qdvc/*.py qdvc/gtk3/*.py qdvc/gtk4/*.py
```

The data layer can be exercised directly, e.g.:

```python
from qdvc import model, config
notes = model.collect_notes("/some/folder")
ordered = model.sort_notes(notes, config.SORT_DATE_NEW)
```

This is a good place to add a real `tests/` directory (pytest) covering
`collect_notes`, `collect_top_level_notes`, `immediate_subfolders`, `sort_notes`,
`parse_headings`, the
`unique_note_path`/`create_empty_note`/`read_note`/`write_note` roundtrip, the
`heading_for_slug`/`slugify`/`rename_note`/`move_note`/`all_subfolders` helpers,
and the `settings` icon-install / `.desktop` / round-trip helpers — none of which
need GTK.

Manual smoke test (needs GTK installed):

1. Launch with a sample folder; confirm sidebar lists All Notes, Inbox, Empty
   Notes, and subfolders one level deep.
2. Select All Notes vs Inbox vs a subfolder; confirm counts in the status bar
   (Inbox shows only top-level notes).
3. Create, edit, save a note; reopen to confirm persistence.
4. Switch sort modes; confirm ordering and that the open note stays selected.
5. Edit without saving, then switch notes / quit; confirm the unsaved prompt.
6. Toggle Read-only/Card view/Preview/Outline from both the toolbar and the View
   menu; confirm they stay in sync. Click outline headings to jump.
7. Set a custom icon set in Preferences; confirm the window icon changes and a
   `qdvc-markdown-notebook` icon appears under `~/.local/share/icons/hicolor`.
8. Enable "reopen last workspace and notes"; quit with a selection and several
   tabs open; relaunch with no argument and confirm panes 1+2 and tabs restore.
