"""
settings.py — persistent user settings for QDVC Markdown Notebook.

Settings are stored as YAML at:

    $XDG_CONFIG_HOME/qdvc-markdown-notebook/config.yml   (if XDG_CONFIG_HOME is set)
    ~/.config/qdvc-markdown-notebook/config.yml          (otherwise)

Configs written by pre-spec builds under the old "qdvcmdnb" subdirectory are
migrated once, on first load, to the canonical location above.

The file is plain text, human-editable, and git-trackable. PyYAML is required;
if it is missing we degrade gracefully to in-memory defaults (a warning is
printed once) so the application still runs.

Schema (version 1):

    version: 1
    editor_font: "monospace 11"        # any Pango font description string
    tab_title_length: 12               # chars before a tab title is ellipsised
    remember_sort: false               # persist the note sort order between runs
    restore_session: false             # reopen last workspace + notes on startup
    icon_set_dir: ""                   # folder of custom app icons (see README)
    sort_mode: alpha                   # persisted sort order (when remember_sort)
    last_workspace: /home/user/notes   # restored on startup (when restore_session)
    last_open_notes:                   # note paths reopened (when restore_session)
      - /home/user/notes/a.md
    last_node: subfolder               # restored sidebar selection (kind)
    last_subfolder: work               # restored subfolder name (if any)
    last_selected_note: /home/user/notes/a.md  # restored pane-2 selection
    recent_folders:                    # most-recent first, capped at MAX_RECENT
      - /home/user/notes
      - /home/user/work/notes

This module has no GTK dependency and is unit-testable without a display.
"""

import os
import sys

try:
    import yaml
    _HAVE_YAML = True
except ImportError:  # pragma: no cover - exercised only without PyYAML
    yaml = None
    _HAVE_YAML = False

# Defaults that match the editor's previous hard-coded behaviour.
DEFAULT_EDITOR_FONT = "monospace 11"
DEFAULT_CODE_FONT = "monospace 11"
DEFAULT_PREVIEW_FONT = "Sans 11"

# Line spacing (pixels of extra space between display lines), applied to the
# editor and the markdown preview respectively.
DEFAULT_EDITOR_LINE_SPACING = 0
DEFAULT_PREVIEW_LINE_SPACING = 4
MIN_LINE_SPACING = 0
MAX_LINE_SPACING = 40

# Toolbar style: icon text beside vs below the icon.
TOOLBAR_TEXT_BESIDE = "beside"
TOOLBAR_TEXT_BELOW = "below"
DEFAULT_TOOLBAR_STYLE = TOOLBAR_TEXT_BELOW

# Tab title length: characters of the note name shown on a tab before it is
# truncated with an ellipsis. Configurable in Preferences.
DEFAULT_TAB_TITLE_LENGTH = 12
MIN_TAB_TITLE_LENGTH = 4
MAX_TAB_TITLE_LENGTH = 80

# Session restore / sort persistence (booleans, default off to preserve the
# previous behaviour where neither was remembered between runs).
DEFAULT_REMEMBER_SORT = False
DEFAULT_RESTORE_SESSION = False

# UI backend selection (spec §3). The dispatcher picks the front-end from a CLI
# flag, then this stored value, then the default. Anything unrecognised falls
# back to gtk3 via the validated `ui_backend` accessor.
UI_BACKEND_GTK3 = "gtk3"
UI_BACKEND_GTK4 = "gtk4"
DEFAULT_UI_BACKEND = UI_BACKEND_GTK3

# Custom icon set: an absolute path to a folder containing 16x16.png, 22x22.png,
# 24x24.png, 32x32.png, 48x48.png, 256x256.png, and scalable.svg. Empty means
# "use the stock accessories-text-editor icon".
DEFAULT_ICON_SET_DIR = ""

# Filenames expected inside a custom icon-set folder. Sizes map a pixel
# dimension to its PNG; the SVG is the scalable fallback.
ICON_SET_PNG_SIZES = (16, 22, 24, 32, 48, 256)
ICON_SET_SVG_NAME = "scalable.svg"

# The themed icon name the app installs a custom icon set under, and the matching
# .desktop file id. Other launchers resolve "Icon=qdvc-markdown-notebook" against
# the user's hicolor theme once the icons are installed.
APP_ICON_NAME = "qdvc-markdown-notebook"
DESKTOP_FILE_ID = "qdvc-markdown-notebook.desktop"

SCHEMA_VERSION = 1
MAX_RECENT = 10

_CONFIG_SUBDIR = "qdvc-markdown-notebook"
_CONFIG_FILENAME = "config.yml"

# Legacy config subdirectory (pre-spec-§5 name). On load, if no config exists at
# the canonical location but one exists here, it is migrated once (see _migrate_
# legacy_config). Retained only for that one-time migration.
_LEGACY_CONFIG_SUBDIR = "qdvcmdnb"

_warned_no_yaml = False


# --------------------------------------------------------------------------- #
# Path resolution
# --------------------------------------------------------------------------- #
def config_dir():
    """Return the directory in which the config file lives (per XDG)."""
    base = os.environ.get("XDG_CONFIG_HOME")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, _CONFIG_SUBDIR)


def config_path():
    """Return the full path to the config file."""
    return os.path.join(config_dir(), _CONFIG_FILENAME)


def _legacy_config_path():
    """Return the full path to the pre-spec-§5 config file (old subdir name)."""
    base = os.environ.get("XDG_CONFIG_HOME")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, _LEGACY_CONFIG_SUBDIR, _CONFIG_FILENAME)


def _migrate_legacy_config():
    """
    One-time migration: if no config exists at the canonical location but one
    exists at the legacy "qdvcmdnb" location, copy it across so upgrading users
    keep their settings. Best-effort — never raises; a failed migration just
    leaves load() to fall back to defaults.
    """
    new_path = config_path()
    if os.path.exists(new_path):
        return
    old_path = _legacy_config_path()
    if not os.path.isfile(old_path):
        return
    try:
        os.makedirs(config_dir(), exist_ok=True)
        with open(old_path, "r", encoding="utf-8") as src:
            data = src.read()
        with open(new_path, "w", encoding="utf-8") as dst:
            dst.write(data)
    except OSError:
        pass


def icon_set_files(folder):
    """
    Given a custom icon-set folder, return a dict mapping each found icon to its
    absolute path: integer pixel sizes (16, 22, …) to their PNG, plus the key
    "scalable" for the SVG. Missing files are simply omitted. An empty/false
    folder, or one that is not a directory, yields an empty dict.

    No GTK here; the window turns these into a Gtk.IconSet / theme additions.
    """
    if not folder or not os.path.isdir(folder):
        return {}
    found = {}
    for size in ICON_SET_PNG_SIZES:
        png = os.path.join(folder, f"{size}x{size}.png")
        if os.path.isfile(png):
            found[size] = png
    svg = os.path.join(folder, ICON_SET_SVG_NAME)
    if os.path.isfile(svg):
        found["scalable"] = svg
    return found


def _data_home():
    """Return $XDG_DATA_HOME or ~/.local/share."""
    base = os.environ.get("XDG_DATA_HOME")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".local", "share")
    return base


def install_icon_set(folder, icon_name=APP_ICON_NAME):
    """
    Copy a custom icon-set folder's files into the user's hicolor icon theme so
    that other launchers (panels, app menus) resolve `Icon=<icon_name>`. PNGs go
    to .../icons/hicolor/<size>x<size>/apps/<icon_name>.png and the SVG to
    .../icons/hicolor/scalable/apps/<icon_name>.svg.

    Returns True if at least one icon was installed, False otherwise (including a
    missing/empty folder). Never raises — best-effort, no GTK. The caller is
    expected to refresh the running Gtk.IconTheme afterwards.
    """
    import shutil
    files = icon_set_files(folder)
    if not files:
        return False
    hicolor = os.path.join(_data_home(), "icons", "hicolor")
    installed = False
    for key, src in files.items():
        if key == "scalable":
            dest_dir = os.path.join(hicolor, "scalable", "apps")
            dest = os.path.join(dest_dir, f"{icon_name}.svg")
        else:
            dest_dir = os.path.join(hicolor, f"{key}x{key}", "apps")
            dest = os.path.join(dest_dir, f"{icon_name}.png")
        try:
            os.makedirs(dest_dir, exist_ok=True)
            shutil.copyfile(src, dest)
            installed = True
        except OSError:
            continue
    return installed


def uninstall_icon_set(icon_name=APP_ICON_NAME):
    """Remove any previously installed custom icons for `icon_name`. Best-effort."""
    hicolor = os.path.join(_data_home(), "icons", "hicolor")
    for size in ICON_SET_PNG_SIZES:
        path = os.path.join(hicolor, f"{size}x{size}", "apps",
                            f"{icon_name}.png")
        try:
            os.remove(path)
        except OSError:
            pass
    svg = os.path.join(hicolor, "scalable", "apps", f"{icon_name}.svg")
    try:
        os.remove(svg)
    except OSError:
        pass


def desktop_file_path():
    """Path to the per-user .desktop file the app maintains its Icon= line in."""
    return os.path.join(_data_home(), "applications", DESKTOP_FILE_ID)


def update_desktop_icon(icon_name, exec_path=None):
    """
    Create or update the per-user .desktop file so its `Icon=` line points at
    `icon_name`. If the file does not exist yet it is created with sensible
    defaults; if it exists only the Icon= line is rewritten (other lines are
    preserved). `exec_path` (absolute path to the script) is used only when
    creating the file. Returns True on success. Never raises.
    """
    path = desktop_file_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
            out = []
            replaced = False
            for line in lines:
                if line.startswith("Icon="):
                    out.append(f"Icon={icon_name}\n")
                    replaced = True
                else:
                    out.append(line)
            if not replaced:
                out.append(f"Icon={icon_name}\n")
            with open(path, "w", encoding="utf-8") as fh:
                fh.writelines(out)
        else:
            exec_line = (f"python3 {exec_path} %F" if exec_path
                         else "qdvc-markdown-notebook %F")
            content = (
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=QDVC Markdown Notebook\n"
                "Comment=Three-pane markdown notebook viewer/editor\n"
                f"Exec={exec_line}\n"
                f"Icon={icon_name}\n"
                "Terminal=false\n"
                "Categories=Office;Utility;TextEditor;\n"
                "MimeType=text/markdown;\n"
                "StartupNotify=true\n"
                "StartupWMClass=qdvc-markdown-notebook\n"
            )
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
        return True
    except OSError:
        return False


def _warn_no_yaml_once():
    global _warned_no_yaml
    if not _warned_no_yaml:
        sys.stderr.write(
            "qdvc-markdown-notebook: PyYAML not installed; settings will not be persisted. "
            "Install it with: pip install pyyaml\n"
        )
        _warned_no_yaml = True


def _coerce_spacing(value, fallback):
    """Validate a line-spacing value: an int clamped to [MIN, MAX]."""
    if isinstance(value, bool):  # bool is an int subclass; reject it explicitly
        return fallback
    if isinstance(value, (int, float)):
        return max(MIN_LINE_SPACING, min(MAX_LINE_SPACING, int(value)))
    return fallback


def _coerce_int_range(value, lo, hi, fallback):
    """Validate an int value clamped to [lo, hi]; reject bools."""
    if isinstance(value, bool):  # bool is an int subclass; reject it explicitly
        return fallback
    if isinstance(value, (int, float)):
        return max(lo, min(hi, int(value)))
    return fallback


def _coerce_bool(value, fallback):
    """Validate a boolean value; non-bools fall back to the default."""
    if isinstance(value, bool):
        return value
    return fallback


# --------------------------------------------------------------------------- #
# Settings object
# --------------------------------------------------------------------------- #
class Settings:
    """
    In-memory view of the user's settings, with load() / save() to disk.

    Always construct via Settings.load(); the bare constructor just holds
    defaults. Unknown keys found in the file are preserved on save so that a
    newer version's settings survive a round-trip through an older build.
    """

    def __init__(self):
        self.editor_font = DEFAULT_EDITOR_FONT
        self.code_font = DEFAULT_CODE_FONT
        self.preview_font = DEFAULT_PREVIEW_FONT
        self.editor_line_spacing = DEFAULT_EDITOR_LINE_SPACING
        self.preview_line_spacing = DEFAULT_PREVIEW_LINE_SPACING
        self.toolbar_style = DEFAULT_TOOLBAR_STYLE
        self.tab_title_length = DEFAULT_TAB_TITLE_LENGTH
        self.remember_sort = DEFAULT_REMEMBER_SORT
        self.restore_session = DEFAULT_RESTORE_SESSION
        # UI backend ("gtk3"/"gtk4"); read via the validated `ui_backend`
        # property so a hand-edited config can never yield an invalid value.
        self._ui_backend = DEFAULT_UI_BACKEND
        self.icon_set_dir = DEFAULT_ICON_SET_DIR
        # Persisted sort mode (one of the SORT_* strings from config). Stored as
        # a plain string here to avoid importing config; the window validates it.
        self.sort_mode = None
        # Last session's workspace + open note paths, for restore-on-startup.
        self.last_workspace = None
        self.last_open_notes = []
        # Last sidebar selection (a NODE_* string) and, for a subfolder, its
        # name; plus the note that was selected in pane 2. Restored with the
        # session when restore_session is on.
        self.last_node = None
        self.last_subfolder = None
        self.last_selected_note = None
        self.recent_folders = []
        self._extra = {}  # forward-compatibility: unrecognised top-level keys

    # ----------------------------------------------------------- loading -- #
    @classmethod
    def load(cls):
        """Load settings from disk, returning a Settings (defaults on any error)."""
        s = cls()
        if not _HAVE_YAML:
            _warn_no_yaml_once()
            return s

        _migrate_legacy_config()
        path = config_path()
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
        except FileNotFoundError:
            return s  # first run; defaults are fine
        except (OSError, yaml.YAMLError) as exc:
            sys.stderr.write(f"qdvc-markdown-notebook: could not read config ({exc}); "
                             f"using defaults\n")
            return s

        if not isinstance(data, dict):
            return s  # empty or malformed file; keep defaults
        s._apply(data)
        return s

    def _apply(self, data):
        """Populate fields from a parsed dict, validating types defensively."""
        font = data.get("editor_font")
        if isinstance(font, str) and font.strip():
            self.editor_font = font

        code_font = data.get("code_font")
        if isinstance(code_font, str) and code_font.strip():
            self.code_font = code_font

        preview_font = data.get("preview_font")
        if isinstance(preview_font, str) and preview_font.strip():
            self.preview_font = preview_font

        self.editor_line_spacing = _coerce_spacing(
            data.get("editor_line_spacing"), self.editor_line_spacing)
        self.preview_line_spacing = _coerce_spacing(
            data.get("preview_line_spacing"), self.preview_line_spacing)

        toolbar_style = data.get("toolbar_style")
        if toolbar_style in (TOOLBAR_TEXT_BESIDE, TOOLBAR_TEXT_BELOW):
            self.toolbar_style = toolbar_style

        self.tab_title_length = _coerce_int_range(
            data.get("tab_title_length"), MIN_TAB_TITLE_LENGTH,
            MAX_TAB_TITLE_LENGTH, self.tab_title_length)

        self.remember_sort = _coerce_bool(
            data.get("remember_sort"), self.remember_sort)
        self.restore_session = _coerce_bool(
            data.get("restore_session"), self.restore_session)

        # ui_backend is stored raw and validated on read (see the property).
        ui_backend = data.get("ui_backend")
        if isinstance(ui_backend, str) and ui_backend.strip():
            self._ui_backend = ui_backend.strip().lower()

        icon_set = data.get("icon_set_dir")
        if isinstance(icon_set, str):
            self.icon_set_dir = icon_set.strip()

        sort_mode = data.get("sort_mode")
        if isinstance(sort_mode, str) and sort_mode.strip():
            self.sort_mode = sort_mode

        last_ws = data.get("last_workspace")
        if isinstance(last_ws, str) and last_ws.strip():
            self.last_workspace = last_ws

        last_notes = data.get("last_open_notes")
        if isinstance(last_notes, list):
            self.last_open_notes = [n for n in last_notes
                                    if isinstance(n, str)]

        last_node = data.get("last_node")
        if isinstance(last_node, str) and last_node.strip():
            self.last_node = last_node
        last_sub = data.get("last_subfolder")
        if isinstance(last_sub, str) and last_sub.strip():
            self.last_subfolder = last_sub
        last_sel = data.get("last_selected_note")
        if isinstance(last_sel, str) and last_sel.strip():
            self.last_selected_note = last_sel

        recents = data.get("recent_folders")
        if isinstance(recents, list):
            self.recent_folders = [r for r in recents if isinstance(r, str)]

        # Preserve any keys we don't recognise (and our known ones are filtered).
        known = {"version", "editor_font", "code_font", "preview_font",
                 "editor_line_spacing", "preview_line_spacing",
                 "toolbar_style", "tab_title_length", "remember_sort",
                 "restore_session", "ui_backend", "icon_set_dir", "sort_mode",
                 "last_workspace", "last_open_notes", "last_node",
                 "last_subfolder", "last_selected_note", "recent_folders"}
        self._extra = {k: v for k, v in data.items() if k not in known}

    # ------------------------------------------------------------ saving -- #
    def to_dict(self):
        d = {
            "version": SCHEMA_VERSION,
            "editor_font": self.editor_font,
            "code_font": self.code_font,
            "preview_font": self.preview_font,
            "editor_line_spacing": self.editor_line_spacing,
            "preview_line_spacing": self.preview_line_spacing,
            "toolbar_style": self.toolbar_style,
            "tab_title_length": self.tab_title_length,
            "remember_sort": self.remember_sort,
            "restore_session": self.restore_session,
            "ui_backend": self.ui_backend,
            "icon_set_dir": self.icon_set_dir,
            "sort_mode": self.sort_mode,
            "last_workspace": self.last_workspace,
            "last_open_notes": list(self.last_open_notes),
            "last_node": self.last_node,
            "last_subfolder": self.last_subfolder,
            "last_selected_note": self.last_selected_note,
            "recent_folders": list(self.recent_folders),
        }
        d.update(self._extra)  # round-trip forward-compatible keys
        return d

    def save(self):
        """Write settings to disk. Returns True on success, False otherwise."""
        if not _HAVE_YAML:
            _warn_no_yaml_once()
            return False
        try:
            os.makedirs(config_dir(), exist_ok=True)
            tmp = config_path() + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                yaml.safe_dump(self.to_dict(), fh,
                               default_flow_style=False, sort_keys=False,
                               allow_unicode=True)
            os.replace(tmp, config_path())  # atomic on POSIX
            return True
        except (OSError, yaml.YAMLError) as exc:
            sys.stderr.write(f"qdvc-markdown-notebook: could not write config ({exc})\n")
            return False

    # ----------------------------------------------------- mutators ----- #
    def set_editor_font(self, font_str):
        if isinstance(font_str, str) and font_str.strip():
            self.editor_font = font_str

    def set_code_font(self, font_str):
        if isinstance(font_str, str) and font_str.strip():
            self.code_font = font_str

    def set_preview_font(self, font_str):
        if isinstance(font_str, str) and font_str.strip():
            self.preview_font = font_str

    def set_editor_line_spacing(self, value):
        self.editor_line_spacing = _coerce_spacing(value,
                                                   self.editor_line_spacing)

    def set_preview_line_spacing(self, value):
        self.preview_line_spacing = _coerce_spacing(value,
                                                    self.preview_line_spacing)

    def set_toolbar_style(self, style):
        if style in (TOOLBAR_TEXT_BESIDE, TOOLBAR_TEXT_BELOW):
            self.toolbar_style = style

    def set_tab_title_length(self, value):
        self.tab_title_length = _coerce_int_range(
            value, MIN_TAB_TITLE_LENGTH, MAX_TAB_TITLE_LENGTH,
            self.tab_title_length)

    def set_remember_sort(self, value):
        self.remember_sort = _coerce_bool(value, self.remember_sort)

    def set_restore_session(self, value):
        self.restore_session = _coerce_bool(value, self.restore_session)

    @property
    def ui_backend(self):
        """
        The validated UI backend, always one of UI_BACKEND_GTK3 /
        UI_BACKEND_GTK4. Anything else stored (e.g. from a hand-edited config)
        reads back as the default gtk3, so the dispatcher can never be handed an
        invalid backend (spec §3).
        """
        val = (self._ui_backend or "").lower()
        if val in (UI_BACKEND_GTK3, UI_BACKEND_GTK4):
            return val
        return DEFAULT_UI_BACKEND

    def set_ui_backend(self, backend):
        if isinstance(backend, str) and backend.strip().lower() in (
                UI_BACKEND_GTK3, UI_BACKEND_GTK4):
            self._ui_backend = backend.strip().lower()

    def set_icon_set_dir(self, path):
        if isinstance(path, str):
            self.icon_set_dir = path.strip()

    def set_sort_mode(self, mode):
        if isinstance(mode, str) and mode.strip():
            self.sort_mode = mode

    def set_last_session(self, workspace, open_notes, node=None,
                         subfolder=None, selected_note=None):
        """
        Record the workspace folder, the open notes, and the sidebar/note-list
        selection for restore-on-startup.
        """
        self.last_workspace = workspace if isinstance(workspace, str) else None
        if isinstance(open_notes, (list, tuple)):
            self.last_open_notes = [n for n in open_notes
                                    if isinstance(n, str)]
        else:
            self.last_open_notes = []
        self.last_node = node if isinstance(node, str) else None
        self.last_subfolder = (subfolder if isinstance(subfolder, str)
                               else None)
        self.last_selected_note = (selected_note
                                   if isinstance(selected_note, str) else None)

    def add_recent_folder(self, folder):
        """
        Record `folder` as the most-recently-used working folder. Moves an
        existing entry to the front (dedup), drops nonexistent dirs, and caps
        the list at MAX_RECENT.
        """
        if not folder:
            return
        folder = os.path.abspath(folder)
        # Drop any existing occurrence, then prepend.
        self.recent_folders = [f for f in self.recent_folders if f != folder]
        self.recent_folders.insert(0, folder)
        # Prune entries that no longer exist on disk.
        self.recent_folders = [
            f for f in self.recent_folders if os.path.isdir(f)
        ]
        del self.recent_folders[MAX_RECENT:]
