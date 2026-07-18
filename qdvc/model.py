"""
model.py — pure-Python data layer for QDVC Markdown Notebook.

No GTK imports here. Everything in this module is testable without a display.
It covers the Note value object, filesystem discovery (subfolders, note
collection), sorting, and all disk read/write/create operations.
"""

import os
import re
import time

from .config import (
    MARKDOWN_EXTENSIONS,
    SORT_ALPHA,
    SORT_DATE_NEW,
    SORT_DATE_OLD,
)


class Note:
    """A single markdown file on disk."""

    __slots__ = ("path", "name", "mtime")

    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        try:
            self.mtime = os.path.getmtime(path)
        except OSError:
            self.mtime = 0.0

    def display_name(self):
        base = self.name
        for ext in MARKDOWN_EXTENSIONS:
            if base.lower().endswith(ext):
                return base[: -len(ext)]
        return base


def is_markdown(filename):
    return filename.lower().endswith(MARKDOWN_EXTENSIONS)


def collect_notes(folder):
    """
    Return a list of Note objects for all markdown files at any depth under
    `folder`. Used for "All Notes" and for an aggregated subfolder view.
    """
    notes = []
    for root, _dirs, files in os.walk(folder):
        for f in files:
            if is_markdown(f):
                notes.append(Note(os.path.join(root, f)))
    return notes


def collect_top_level_notes(folder):
    """
    Return Note objects for markdown files directly inside `folder` only (no
    recursion). Backs the sidebar's *Inbox* node: notes that haven't been filed
    into a subfolder yet.
    """
    notes = []
    try:
        entries = os.listdir(folder)
    except OSError:
        return notes
    for name in entries:
        full = os.path.join(folder, name)
        if is_markdown(name) and os.path.isfile(full):
            notes.append(Note(full))
    return notes


def note_is_empty(note):
    """
    Return True if `note`'s content is empty or entirely whitespace. Unreadable
    files are treated as not-empty (so they aren't silently hidden/altered).
    """
    try:
        return read_note(note).strip() == ""
    except (OSError, UnicodeDecodeError):
        return False


def collect_empty_notes(folder):
    """All notes under `folder` whose content is empty or all whitespace."""
    return [n for n in collect_notes(folder) if note_is_empty(n)]


def note_matches(note, query_lower):
    """
    Return True if `query_lower` (already lowercased) occurs, case-insensitively,
    in either the note's display name or its file contents.

    Reads the file on demand. Unreadable files fall back to matching the name
    only, so a transient read error doesn't make a note vanish from results.
    """
    if query_lower in note.display_name().lower():
        return True
    try:
        return query_lower in read_note(note).lower()
    except (OSError, UnicodeDecodeError):
        return False


def filter_notes(notes, query):
    """
    Filter `notes` to those matching `query` (case-insensitive) in name or
    contents. A blank/None query returns the list unchanged.
    """
    q = (query or "").strip().lower()
    if not q:
        return list(notes)
    return [n for n in notes if note_matches(n, q)]


def immediate_subfolders(root):
    """Return sorted list of immediate subfolder names of `root`."""
    try:
        entries = os.listdir(root)
    except OSError:
        return []
    subs = [
        e for e in entries
        if os.path.isdir(os.path.join(root, e)) and not e.startswith(".")
    ]
    return sorted(subs, key=str.lower)


def sort_notes(notes, sort_mode):
    """Return a new list of notes ordered according to `sort_mode`."""
    if sort_mode == SORT_ALPHA:
        return sorted(notes, key=lambda n: n.display_name().lower())
    if sort_mode == SORT_DATE_NEW:
        return sorted(notes, key=lambda n: n.mtime, reverse=True)
    if sort_mode == SORT_DATE_OLD:
        return sorted(notes, key=lambda n: n.mtime)
    return list(notes)


# --------------------------------------------------------------------------- #
# Disk I/O
#
# These functions raise OSError / UnicodeDecodeError on failure; the caller
# (the window) is responsible for presenting errors to the user. Keeping the
# I/O here means the view never touches the filesystem directly.
# --------------------------------------------------------------------------- #
def read_note(note):
    """Read and return the text content of `note`. May raise."""
    with open(note.path, "r", encoding="utf-8") as fh:
        return fh.read()


def first_body_line(note):
    """
    Return the first non-empty line of `note` that follows the leading heading,
    for the card-view preview line. If the note starts with a level-1..6 heading
    (`#`..`######`), that heading line is skipped; the first non-blank line after
    it is returned. If there is no heading, the first non-blank line is returned.
    Returns "" on an empty note or read error.
    """
    try:
        content = read_note(note)
    except (OSError, UnicodeDecodeError):
        return ""
    lines = content.split("\n")
    idx = 0
    # Skip leading blank lines.
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1
    # If the first non-blank line is a heading, skip it.
    if idx < len(lines) and re.match(r"^#{1,6}\s+\S", lines[idx]):
        idx += 1
    # Return the next non-blank line.
    while idx < len(lines):
        stripped = lines[idx].strip()
        if stripped:
            return stripped
        idx += 1
    return ""


def format_mtime_value(mtime):
    """Human-readable date for a raw mtime float (for card view)."""
    if not mtime:
        return ""
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))


def format_mtime(note):
    """Human-readable last-modified date for `note` (for card view)."""
    return format_mtime_value(note.mtime)


def write_note(note, content):
    """
    Write `content` to `note` on disk and refresh its mtime. May raise.

    Writes are not atomic; see MAINTENANCE.md for the os.replace upgrade path.
    """
    with open(note.path, "w", encoding="utf-8") as fh:
        fh.write(content)
    note.mtime = time.time()


def unique_note_path(folder, base="Untitled", ext=".md"):
    """
    Return a path inside `folder` for a new note that does not collide with an
    existing file: 'Untitled.md', 'Untitled 1.md', 'Untitled 2.md', ...
    """
    candidate = os.path.join(folder, base + ext)
    i = 1
    while os.path.exists(candidate):
        candidate = os.path.join(folder, f"{base} {i}{ext}")
        i += 1
    return candidate


def create_empty_note(folder, base="Untitled", ext=".md"):
    """Create a new empty note file in `folder` and return its path. May raise."""
    path = unique_note_path(folder, base=base, ext=ext)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("")
    return path


# --------------------------------------------------------------------------- #
# Slug / rename helpers
# --------------------------------------------------------------------------- #
_H1_RE = re.compile(r"^#\s+(\S.*?)\s*$")
SLUG_MAX_HEADING_LEN = 32


def heading_for_slug(text):
    """
    If `text`'s first line is a markdown level-1 heading (`# ...`) whose heading
    content is shorter than SLUG_MAX_HEADING_LEN characters, return that heading
    text. Otherwise return None.

    Note the length test is on the heading *content* (after "# "), matching the
    user-visible title; "less than 32" is strict (< 32).
    """
    first_line = text.split("\n", 1)[0]
    m = _H1_RE.match(first_line)
    if not m:
        return None
    heading = m.group(1)
    if len(heading) >= SLUG_MAX_HEADING_LEN:
        return None
    return heading


def slugify(heading):
    """
    Turn a heading into a filename slug: lowercase, only [a-z] and dashes.
    Runs of non-alphabetic characters collapse to a single dash; leading and
    trailing dashes are stripped. E.g. "My awesome new note!" -> "my-awesome-new-note".
    Returns "" if nothing usable remains.
    """
    lowered = heading.lower()
    # Replace any run of characters that are not a-z with a single dash.
    slug = re.sub(r"[^a-z]+", "-", lowered)
    return slug.strip("-")


def rename_note(note, new_basename, ext=".md"):
    """
    Rename `note` on disk to `new_basename + ext` within the same directory,
    avoiding collisions via unique_note_path. Updates the Note's path/name in
    place and returns the new path. May raise OSError.

    If the target equals the current path (already correctly named), this is a
    no-op that returns the current path.
    """
    folder = os.path.dirname(note.path)
    desired = os.path.join(folder, new_basename + ext)
    if os.path.abspath(desired) == os.path.abspath(note.path):
        return note.path
    target = unique_note_path(folder, base=new_basename, ext=ext)
    os.rename(note.path, target)
    note.path = target
    note.name = os.path.basename(target)
    return target


def move_note(note, dest_folder):
    """
    Move `note` into `dest_folder`, keeping its filename and avoiding collisions
    via unique_note_path. Updates the Note's path/name in place and returns the
    new path. A no-op (returns the current path) if it already lives there.
    May raise OSError.
    """
    if not os.path.isdir(dest_folder):
        raise OSError(f"Not a folder: {dest_folder}")
    if os.path.abspath(os.path.dirname(note.path)) == os.path.abspath(dest_folder):
        return note.path
    base, ext = os.path.splitext(note.name)
    target = unique_note_path(dest_folder, base=base, ext=ext or ".md")
    os.rename(note.path, target)
    note.path = target
    note.name = os.path.basename(target)
    return target


def all_subfolders(root):
    """
    Return a sorted list of every subfolder under `root` at any depth, as paths
    relative to `root` (e.g. "work", "work/2026"). Hidden directories (and any
    of their descendants) are excluded. Used to build the "Move to subfolder"
    submenu, so the root itself is included first as "" (meaning the top level).
    """
    results = [""]
    for cur, dirs, _files in os.walk(root):
        # Prune hidden directories in place so we don't descend into them.
        dirs[:] = sorted((d for d in dirs if not d.startswith(".")),
                         key=str.lower)
        for d in dirs:
            full = os.path.join(cur, d)
            rel = os.path.relpath(full, root)
            results.append(rel)
    return results


# --------------------------------------------------------------------------- #
# Headings outline
# --------------------------------------------------------------------------- #
_ATX_HEADING_RE = re.compile(r"^(#{1,6})\s+(\S.*?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")


def parse_headings(text):
    """
    Parse ATX markdown headings (`#`..`######`) out of `text` for the outline
    pane. Returns a list of dicts: {"level": int 1..6, "title": str, "line":
    int 0-based line index of the heading}.

    Fenced code blocks (``` or ~~~) are skipped so a `#` comment inside code is
    not mistaken for a heading. Trailing `#` (closed ATX headings) are stripped
    from the title. Pure text→list, no GTK, so it is unit-testable.
    """
    headings = []
    in_fence = False
    fence_marker = None
    for idx, line in enumerate(text.split("\n")):
        fence = _FENCE_RE.match(line)
        if fence:
            marker = fence.group(1)
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = None
            continue
        if in_fence:
            continue
        m = _ATX_HEADING_RE.match(line)
        if m:
            headings.append({
                "level": len(m.group(1)),
                "title": m.group(2).strip(),
                "line": idx,
            })
    return headings
