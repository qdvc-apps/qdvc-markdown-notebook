# MAINTENANCE_GTK3_GTK4.md

Element-by-element map between the GTK 3 and GTK 4 front-ends of QDVC Markdown
Notebook, plus the list-model / data-binding cheat-sheet. This document is the
companion required by the common spec §12; for shared conventions see the
specification itself:
<https://github.com/qdvc-apps/qdvc-python-gtk-app-specification/>.

Both front-ends sit on the **same pure core** (`qdvc/config.py`, `model.py`,
`settings.py`, `pango_markdown.py`, `strings.py`, `ui_prefs.py`,
`platform_utils.py`, `highlight_rules.py`) and must not reimplement model, file,
naming, or formatting logic. Only the view mechanics differ.

## 1. Module map

| Concern | GTK 3 (`qdvc/gtk3/`) | GTK 4 (`qdvc/gtk4/`) |
| --- | --- | --- |
| Application | `gtk3_app.NotebookApp` (`Gtk.Application`) | `gtk4_app.NotebookApp` (`Adw.Application`) |
| Main window | `gtk3_window.NotebookWindow` (`Gtk.ApplicationWindow`) | `gtk4_window.NotebookWindow` (`Adw.ApplicationWindow`) |
| Commands | menu/toolbar handlers + `Gtk.AccelGroup` | `win.*` `Gio.SimpleAction`s (`gtk4_actions.ActionsMixin`) |
| Menu surface | `gtk3_menubar.MenuBarMixin` (menubar) | primary menu `Gio.Menu` in `gtk4_window` |
| Toolbar | `gtk3_toolbar.ToolbarMixin` | header buttons in `Adw.HeaderBar` (no toolbar) |
| Panes / binding | `gtk3_panes.PanesMixin` | `_build_*` in `gtk4_window` |
| Handlers/dialogs | `gtk3_actions.ActionsMixin` | `on_*` in `gtk4_window` (+ `gtk4_actions`) |
| Editor tab | `gtk3_editortab.EditorTab` | `gtk4_editorview.EditorView` |
| Highlighter | `gtk3_highlighter.MarkdownHighlighter` | `gtk4_highlighter.MarkdownHighlighter` |
| Preferences | `gtk3_preferences.PreferencesDialog` | `gtk4_preferences.PreferencesWindow` |
| Shortcuts | `gtk3_shortcuts` (accel wiring) | `gtk4_shortcuts` (shortcuts window) |

Both highlighters share the pure `highlight_rules` module (regexes, tag specs,
`iter_spans`); each only translates spans into its toolkit's `Gtk.TextBuffer`
tags — which happen to use the same API in GTK 3 and GTK 4.

## 2. Element-by-element substitutions

| Element | GTK 3 | GTK 4 / libadwaita |
| --- | --- | --- |
| Window chrome | title bar + `Gtk.MenuBar` + `Gtk.Toolbar` + statusbar | `Adw.ToolbarView`: `Adw.HeaderBar` top, content, status label bottom |
| Command model | per-widget `connect("activate")` + `Gtk.AccelGroup` | one `Gio.SimpleAction` per command under `win.`; menu + button reference it by name |
| Accelerators | `add_accelerator(...)` from `ui_prefs` via `gtk3_shortcuts.add_menu_accel` | `Gtk.Application.set_accels_for_action` from `ui_prefs` in `gtk4_app` |
| Menu | `Gtk.MenuBar` with `Gtk.ImageMenuItem`s | primary `Gtk.MenuButton` (`open-menu-symbolic`, `set_primary(True)`) + `Gio.Menu` |
| View toggles | `Gtk.ToggleToolButton` + `Gtk.CheckMenuItem` synced pair | stateful boolean `Gio.SimpleAction`s bound to `Gtk.ToggleButton` + menu items; the preview toggle uses a spectacles/reading-glasses icon (resolved with a fallback chain) so it doesn't resemble the copy icon |
| Editor tabs | `Gtk.Notebook` of `EditorTab.widget`; hand-built tab label + close button | `Adw.TabView` + `Adw.TabBar`; `Adw.TabPage` owns the title/close |
| Note list | `Gtk.TreeView` + `Gtk.ListStore` + cell-data-func | `Gtk.ListView` + `Gio.ListStore` of `NoteItem` + `Gtk.SignalListItemFactory`, inside a `Gtk.FilterListModel` + `Gtk.CustomFilter`. Row labels ellipsize and the scroller has `propagate_natural_width=False` so a wide card can't force the pane wider; each pane child has a `width_request` minimum so none can be collapsed to invisibility |
| Note context menu | `Gtk.Menu` popup from a pane-2 right-click / tab right-click | `Gtk.PopoverMenu` from a `Gio.Menu` model, raised by a `Gtk.GestureClick` (button 3) on each row; items target parameterized `win.note-*` actions carrying the note path (move carries `src\ndest`). Includes Slugify (the only route to slugify in GTK 4) |
| Recent workspaces | File-menu submenu refilled from `settings.recent_folders` | a dedicated **header menu-button** with its own popover `Gio.Menu` (refilled by `_rebuild_recent_menu`); kept out of the primary menu so long paths never widen it. Entries target `win.open-recent` with the folder path |
| Custom app icon | `set_icon_list` from pixbufs + hicolor install + `.desktop` rewrite | hicolor install + icon-theme search-path + `.desktop` rewrite + `set_default_icon_name`/`set_icon_name(APP_ICON_NAME)` (GTK 4 keeps both) so the MATE panel / Alt+Tab resolve it |
| Window title | `Gtk.MessageDialog` + entry (OK/Reset/Cancel), `_custom_title` | async `Adw.MessageDialog` + `Gtk.Entry` extra-child, `win.set-window-title` action; same `_custom_title` session-only field and `_update_window_title` precedence |
| About icon | `set_logo`/`set_logo_icon_name` resolving custom → themed → stock | `Adw.AboutWindow.set_application_icon` with `APP_ICON_NAME` when a custom set is installed, else the stock themed name |
| Sidebar | `Gtk.TreeView` tree (`Gtk.TreeStore`) | `Gtk.ListView` + `Gio.ListStore` of `SidebarRow` + `Gtk.SingleSelection` |
| Outline | `Gtk.TreeView` (`Gtk.TreeStore`) | `Gtk.ListView` + `Gio.ListStore` of `OutlineItem` (indent encoded in label) |
| Fonts | `TextView.override_font(Pango.FontDescription)` | CSS via a `Gtk.CssProvider` (`override_font` removed in GTK 4); `.qdvc-editor` / `.qdvc-preview` classes |
| Tab→spaces | `connect("key-press-event")` | `Gtk.EventControllerKey` `key-pressed` |
| Modal dialogs | `dialog.run()` (blocking) | async: `Gtk.FileDialog` / `Adw.MessageDialog` + response callbacks (no `run()`) |
| Preferences | tabbed `Gtk.Dialog`, Save/Cancel snapshot-revert | `Adw.PreferencesWindow`, **live-apply**, no toolbar-style row, backend `Adw.ComboRow` |
| About | `Gtk.AboutDialog` | `Adw.AboutWindow` (falls back to `Gtk.AboutDialog`) |
| Shortcuts help | (none in GTK 3) | `Gtk.ShortcutsWindow` from `ui_prefs.grouped_shortcuts` (`win.show-help-overlay`) |
| Quit | close window → `Gtk.Application` exits (standalone: `Gtk.main_quit`) | `app.quit()` after async confirm |

## 3. List-model / data-binding cheat-sheet (GTK 4)

The GTK 4 list widgets follow the standard factory pattern:

```
Gio.ListStore(item_type=RowGObject)          # the data (rows are GObjects)
  → Gtk.FilterListModel(model, filter)       # optional: search filtering
      → Gtk.SingleSelection(model)           # selection state
          → Gtk.ListView(model, factory)     # the view
Gtk.SignalListItemFactory:
    "setup" → build the row widget tree once
    "bind"  → copy the row GObject's fields into that widget
```

Row GObjects in this app: `NoteItem` (note list), `SidebarRow` (sidebar),
`OutlineItem` (outline). Search is a `Gtk.CustomFilter` whose predicate calls the
pure `model.note_matches`; changing `search_query` triggers
`filter.changed(Gtk.FilterChange.DIFFERENT)`.

## 4. Deliberate GTK 4 choices worth knowing

- **`Adw.TabView` for editor tabs, not `Adw.ViewStack`.** The spec (§9) says a
  *multi-view* app uses `Adw.ViewStack` + `Adw.ViewSwitcher`. Here the tabs are
  **documents**, not top-level app views, so `Adw.TabView` / `Adw.TabBar` is the
  HIG-correct widget; `ViewStack` is for switching between distinct app modes,
  which this app does not have. This is a reasoned reading of §9, not a
  deviation from it.
- **Fonts via CSS.** GTK 4 removed `override_font`, so the window owns a
  `Gtk.CssProvider` and the editor/preview `TextView`s carry CSS classes; the
  Pango font-description string from settings is translated to a CSS
  `font-family` / `font-size` rule.
- **Per-tab read-only / preview** state lives on each `EditorView`, exactly as
  in GTK 3; the window mirrors the active view's state onto the stateful actions
  so the header toggles reflect the current tab.

## 5. Parity checklist when adding a feature (spec §14)

1. Put toolkit-independent logic in the pure layer (`ui_prefs`, a domain module,
   or `highlight_rules`).
2. Implement the view change in **both** `gtk3_*` and `gtk4_*` (or document the
   exception).
3. Add the command to the GTK 3 menu/toolbar **and** install a matching `win.*`
   `Gio.SimpleAction` in `gtk4_actions`, referenced by name from the GTK 4 menu /
   header; add its accelerator to `ui_prefs.SHORTCUTS`.
4. Wire sensitivity into GTK 3 (`_update_save_sensitivity` /
   `_update_slugify_sensitivity`) and GTK 4 (`_update_actions_sensitivity`).

## 6. Display-free testing (spec §13)

- Pure-model tests run against the core with no display.
- A permissive fake-`gi` stub lets every module under `qdvc/gtk3/` and
  `qdvc/gtk4/` import, exercising class bodies and top-level code. Because such a
  stub cannot evaluate real enum values, keep enum-derived constants out of class
  scope (the highlighters read Pango enums inside methods, and the note/​sidebar
  row GObjects declare only data attributes).

```sh
python3 -m py_compile qdvc/*.py qdvc/gtk3/*.py qdvc/gtk4/*.py qdvc_markdown_notebook.py
# then the stub-import of every qdvc.gtk3.* and qdvc.gtk4.* module
```
