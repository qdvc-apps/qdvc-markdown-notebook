"""
settings.py — persistent user settings for QDVC Markdown Notebook.

Settings are stored as YAML at:

    $XDG_CONFIG_HOME/qdvcmdnb/config.yml      (if XDG_CONFIG_HOME is set)
    ~/.config/qdvcmdnb/config.yml             (otherwise)

The file is plain text, human-editable, and git-trackable. PyYAML is required;
if it is missing we degrade gracefully to in-memory defaults (a warning is
printed once) so the application still runs.

Schema (version 1):

    version: 1
    editor_font: "monospace 11"        # any Pango font description string
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

# Toolbar style: icon text beside vs below the icon.
TOOLBAR_TEXT_BESIDE = "beside"
TOOLBAR_TEXT_BELOW = "below"
DEFAULT_TOOLBAR_STYLE = TOOLBAR_TEXT_BELOW

SCHEMA_VERSION = 1
MAX_RECENT = 10

_CONFIG_SUBDIR = "qdvcmdnb"
_CONFIG_FILENAME = "config.yml"

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


def _warn_no_yaml_once():
    global _warned_no_yaml
    if not _warned_no_yaml:
        sys.stderr.write(
            "qdvcmdnb: PyYAML not installed; settings will not be persisted. "
            "Install it with: pip install pyyaml\n"
        )
        _warned_no_yaml = True


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
        self.toolbar_style = DEFAULT_TOOLBAR_STYLE
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

        path = config_path()
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
        except FileNotFoundError:
            return s  # first run; defaults are fine
        except (OSError, yaml.YAMLError) as exc:
            sys.stderr.write(f"qdvcmdnb: could not read config ({exc}); "
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

        toolbar_style = data.get("toolbar_style")
        if toolbar_style in (TOOLBAR_TEXT_BESIDE, TOOLBAR_TEXT_BELOW):
            self.toolbar_style = toolbar_style

        recents = data.get("recent_folders")
        if isinstance(recents, list):
            self.recent_folders = [r for r in recents if isinstance(r, str)]

        # Preserve any keys we don't recognise (and our known ones are filtered).
        known = {"version", "editor_font", "code_font", "toolbar_style",
                 "recent_folders"}
        self._extra = {k: v for k, v in data.items() if k not in known}

    # ------------------------------------------------------------ saving -- #
    def to_dict(self):
        d = {
            "version": SCHEMA_VERSION,
            "editor_font": self.editor_font,
            "code_font": self.code_font,
            "toolbar_style": self.toolbar_style,
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
            sys.stderr.write(f"qdvcmdnb: could not write config ({exc})\n")
            return False

    # ----------------------------------------------------- mutators ----- #
    def set_editor_font(self, font_str):
        if isinstance(font_str, str) and font_str.strip():
            self.editor_font = font_str

    def set_code_font(self, font_str):
        if isinstance(font_str, str) and font_str.strip():
            self.code_font = font_str

    def set_toolbar_style(self, style):
        if style in (TOOLBAR_TEXT_BESIDE, TOOLBAR_TEXT_BELOW):
            self.toolbar_style = style

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
