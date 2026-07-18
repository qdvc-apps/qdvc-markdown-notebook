"""
strings.py — all user-facing UI text in one place (core; no GTK).

Every human-readable string the GTK layer shows the user lives here, grouped by
the part of the UI it belongs to. The GTK modules import these names instead of
hard-coding literals, so a future translation effort has a single file to work
from.

Why a plain module of constants (rather than gettext today)?
  * It is the prerequisite step: collecting every string in one place.
  * It needs no extra runtime dependency and stays import-safe with no display.
  * It migrates cleanly later: to add gettext, wrap the literals below in `_()`
    and install a translation domain; call sites need not change because they
    already reference these names, not the literals.

Conventions:
  * Names are grouped under small classes used purely as namespaces (e.g.
    `Menu.FILE`, `Toolbar.SAVE`). The classes are never instantiated.
  * A few strings contain format placeholders; these are exposed as functions
    (e.g. `status_items`, `confirm_move_body`) so callers pass values in and the
    word order can change per language. Keeping the `.format`/f-string inside
    this module means translators control placement, not the call site.
  * Unicode is written with explicit escapes (e.g. \u2026 for an ellipsis,
    \u201c/\u201d for curly quotes) to match the literals previously inline.
  * Strings with a leading underscore + letter (e.g. "_File") use GTK mnemonics:
    the character after the underscore becomes the Alt-access key. This is a
    display concern but is kept here so translators can move the accelerator to
    a sensible letter in their language.
"""


# --- application identity ---------------------------------------------------- #
# APP_NAME itself lives in config.py because it doubles as the program/WM identity
# (set_prgname, window title prefix), not only display text. It is re-exported
# here for convenience so translation work can find it alongside the rest.
from .config import APP_NAME  # noqa: F401  (re-export; see __all__ below)

# Names this module deliberately re-exports / exposes. Listing APP_NAME here
# documents that the import above is an intentional re-export, not dead code.
__all__ = ["APP_NAME", "APP_COMMENTS", "Menu", "Toolbar", "Sidebar", "Editor",
           "Status", "Prefs", "Dialog", "status_items", "status_no_results",
           "status_tab_position"]

# A one-line description shown in the About dialog.
APP_COMMENTS = "A three-pane markdown notebook for the MATE / GNOME2-era desktop."


class Menu:
    """Menu-bar labels. The `_X` underscore marks the Alt-mnemonic letter."""

    # Top-level menus.
    FILE = "_File"
    EDIT = "_Edit"
    VIEW = "_View"
    HELP = "_Help"

    # File menu.
    NEW_NOTE = "New note"
    SAVE_NOTE = "Save note"
    REFRESH_NOTE = "Refresh note"
    OPEN_WORKSPACE = "Open workspace"
    REFRESH_WORKSPACE = "Refresh workspace"
    CLOSE_WORKSPACE = "Close workspace"
    OPEN_RECENT_WORKSPACE = "Open recent workspace"
    NEW_TAB = "New tab"
    CLOSE_TAB = "Close tab"
    QUIT = "Quit"
    # Placeholder row shown when the recent-workspaces submenu is empty.
    RECENT_NONE = "(none)"

    # Edit menu.
    PREFERENCES = "Preferences\u2026"
    SET_WINDOW_TITLE = "Set window title\u2026"

    # View menu (check/radio items).
    TOOLBAR = "Toolbar"
    STATUSBAR = "Statusbar"
    READ_ONLY = "Read-only"
    CARD_VIEW = "Card view"
    PREVIEW = "Preview"
    OUTLINE = "Headings outline"
    SORT_ALPHA = "Sort: Alphabetical"
    SORT_DATE_NEW = "Sort: Date, newest first"
    SORT_DATE_OLD = "Sort: Date, oldest first"

    # Help menu.
    ABOUT = "About"


class Toolbar:
    """Toolbar button labels and their hover tooltips."""

    NEW_TAB = "New tab"
    NEW_TAB_TIP = "Open a new tab"
    NEW_NOTE = "New note"
    NEW_NOTE_TIP = "Create a new note in the selected folder"
    SAVE_NOTE = "Save note"
    SAVE_NOTE_TIP = "Save the current note"
    REFRESH_NOTE = "Refresh note"
    REFRESH_NOTE_TIP = "Reload the current note from disk"
    SLUGIFY = "Slugify"
    SLUGIFY_TIP = "Rename this note from its level-1 heading"
    CARD_VIEW = "Card view"
    CARD_VIEW_TIP = "Show notes as cards (title, date, first line)"
    READ_ONLY = "Read-only"
    READ_ONLY_TIP = "Read-only mode (release to edit)"
    PREVIEW = "Preview"
    PREVIEW_TIP = "Preview rendered markdown (read-only)"
    OUTLINE = "Outline"
    OUTLINE_TIP = "Show the headings outline of the current note"
    SET_TITLE = "Window title"
    SET_TITLE_TIP = "Set a custom window title"


class Sidebar:
    """Sidebar (pane 1) node labels and the note-list / outline column titles."""

    ALL_NOTES = "All Notes"
    INBOX = "Inbox"
    EMPTY_NOTES = "Empty Notes"
    SUBFOLDERS = "Subfolders"
    # Column header for the sidebar tree itself (headers are hidden, but the
    # title is still set, so it lives here for completeness).
    FOLDERS_COLUMN = "Folders"
    # Note-list (pane 2) column header and its placeholder.
    NOTES_COLUMN = "Notes"
    SEARCH_PLACEHOLDER = "Search notes\u2026"
    SEARCH_BUTTON = "Search"
    NOTELIST_PLACEHOLDER = "Select a folder or note"
    # Outline (pane 4) column header.
    OUTLINE_COLUMN = "Outline"


class Editor:
    """EditorTab labels and the empty-tab placeholder."""

    UNTITLED = "Untitled"
    CLOSE_TAB_TIP = "Close tab"
    UNSAVED_TOOLTIP = "Unsaved note"
    # The dim message shown in a tab that has no note open. Two parts so the
    # markup wrapper (size/colour) can stay in the GTK layer.
    EMPTY_PLACEHOLDER = "Select a note to start reading or editing"


class Status:
    """Status-bar text. The mode labels are shown bold (markup added by caller)."""

    MODE_PREVIEW = "Rendered Markdown preview"
    MODE_READ_ONLY = "Read-only mode"
    MODE_EDIT = "Edit mode"
    SELECTED_NONE = "none"


def status_items(count, selected):
    """Status text: item count + current selection (no search active)."""
    return f"{count} item(s)  |  Selected: {selected}"


def status_no_results(selected):
    """Status text shown when a search matched nothing."""
    return f"No search results found!  |  Selected: {selected}"


def status_tab_position(current, total):
    """The trailing 'Tab n/m' fragment appended when more than one tab is open."""
    return f"  |  Tab {current}/{total}"


class Prefs:
    """Preferences dialog labels."""

    TITLE = "Preferences"
    TAB_FONTS = "Fonts"
    TAB_INTERFACE = "Interface"

    # Fonts tab.
    EDITOR_FONT = "Editor font:"
    CODE_FONT = "Code font:"
    PREVIEW_FONT = "Markdown preview font:"
    EDITOR_LINE_SPACING = "Editor line spacing:"
    PREVIEW_LINE_SPACING = "Preview line spacing:"

    # Interface tab.
    TOOLBAR_TEXT_PLACEMENT = "Toolbar icon text placement:"
    TOOLBAR_TEXT_BELOW = "Below each icon"
    TOOLBAR_TEXT_BESIDE = "Beside each icon"
    TAB_TITLE_LENGTH = "Tab title length (characters):"
    REMEMBER_SORT = "Remember note sort order between sessions"
    RESTORE_SESSION = "Reopen last workspace and notes on startup"
    ICON_SET_LABEL = "Custom application icon set (folder):"
    ICON_SET_CHOOSER_TITLE = "Choose icon-set folder"
    ICON_SET_CLEAR = "Clear"
    ICON_SET_CLEAR_TIP = "Revert to the default app icon"
    # Hint under the icon-set chooser (wrapped in <small> markup by the caller).
    ICON_SET_HINT = ("Folder must contain 16x16.png, 22x22.png, 24x24.png, "
                     "32x32.png, 48x48.png, 256x256.png and scalable.svg. Takes "
                     "full effect on next launch.")

    # UI backend selector (GTK4 Preferences; spec §3/§9).
    UI_BACKEND_LABEL = "User-interface toolkit:"
    UI_BACKEND_SUBTITLE = "Takes effect after restart."
    UI_BACKEND_GTK3 = "GTK 3 (MATE / classic)"
    UI_BACKEND_GTK4 = "GTK 4 / libadwaita (modern)"
    # Adwaita preference group headings.
    GROUP_FONTS = "Fonts"
    GROUP_SPACING = "Spacing"
    GROUP_INTERFACE = "Interface"
    GROUP_SESSION = "Session"


class Dialog:
    """Dialog titles, prompts, button labels, and error messages.

    Buttons whose label starts with `_` use a GTK mnemonic (Alt-access key).
    Messages with placeholders are functions so word order can be translated.
    """

    # File chooser (Open workspace).
    OPEN_FOLDER_TITLE = "Open Working Folder"
    BTN_CANCEL = "_Cancel"
    BTN_OPEN = "_Open"
    BTN_SAVE = "_Save"
    BTN_DISCARD = "Discard"
    BTN_OK = "_OK"
    BTN_RESET = "_Reset to default"

    # Set custom window title.
    SET_TITLE_HEADING = "Set window title"
    SET_TITLE_PROMPT = ("Enter a custom window title, or leave blank / reset to "
                        "use the default.")

    # Move / rename confirmations (primary lines).
    MOVE_TITLE = "Move this note?"
    RENAME_TITLE = "Rename this note?"

    # Context-menu items.
    OPEN_IN_NEW_TAB = "Open in new tab"
    SLUGIFY = "Slugify (rename from heading)"
    MOVE_TO_SUBFOLDER = "Move to subfolder"
    LOCATE_IN_SUBFOLDERS = "Locate in subfolders"
    COPY_FULL_PATH = "Copy full path"
    SHOW_IN_FILE_BROWSER = "Show in file browser"
    MOVE_SUBMENU_TOP_LEVEL = "(top level)"
    MOVE_SUBMENU_NO_WORKSPACE = "(open a workspace first)"

    # Notices / errors.
    READ_ONLY_NOTICE = ("Read-only mode is on. Release the Read-only button to "
                        "make changes.")
    NO_WORKSPACE = "Open a working folder first (Ctrl+O)."

    @staticmethod
    def workspace_missing(path):
        return f"Working folder no longer exists:\n{path}"

    @staticmethod
    def not_a_folder(path):
        return f"Not a folder:\n{path}"

    @staticmethod
    def recent_missing(path):
        return f"Folder no longer exists:\n{path}"

    @staticmethod
    def confirm_move_body(name, destination):
        return (f"\u201c{name}\u201d will be moved to "
                f"\u201c{destination}\u201d.")

    @staticmethod
    def confirm_rename_body(old_name, new_name):
        return (f"\u201c{old_name}\u201d will be renamed to "
                f"\u201c{new_name}\u201d.")

    @staticmethod
    def save_changes_prompt(name):
        return f"Save changes to \u201c{name}\u201d?"

    @staticmethod
    def err_move(detail):
        return f"Could not move note:\n{detail}"

    @staticmethod
    def err_create(detail):
        return f"Could not create note:\n{detail}"

    @staticmethod
    def err_reload(path):
        return f"Could not reload note:\n{path}"

    @staticmethod
    def err_rename(detail):
        return f"Could not rename note:\n{detail}"

    @staticmethod
    def err_open(path):
        return f"Could not open note:\n{path}"

    @staticmethod
    def err_save(path):
        return f"Could not save note:\n{path}"

    @staticmethod
    def err_file_browser(detail):
        return f"Could not open file browser:\n{detail}"
