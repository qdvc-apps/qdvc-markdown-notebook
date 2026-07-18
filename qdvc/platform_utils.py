"""
platform_utils.py — launch system applications (viewer, editor, file manager).

PURE module (no GTK): branches on ``sys.platform`` / ``os.name`` so both
front-ends share one implementation (spec §11). Every function is best-effort
and returns a bool indicating whether a launcher was successfully spawned; none
raises for an ordinary "command not found" / spawn failure.

The GTK front-ends MAY prefer a toolkit-native opener (e.g. GTK's
``show_uri_on_window``) for the common "reveal in file manager" case; this
module is the toolkit-independent fallback and the home of the configurable
file-manager template.
"""

import os
import shlex
import subprocess
import sys


def _spawn(argv):
    """Spawn a detached process. Returns True on success, False on any error."""
    try:
        subprocess.Popen(argv,
                         stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        return True
    except (OSError, ValueError):
        return False


def open_with_default_app(path):
    """Open `path` in the platform's default application for its type."""
    if sys.platform == "darwin":
        return _spawn(["open", path])
    if os.name == "nt":  # pragma: no cover - not the target platform
        try:
            os.startfile(path)  # type: ignore[attr-defined]
            return True
        except OSError:
            return False
    # Linux / other POSIX.
    return _spawn(["xdg-open", path])


def open_with_text_editor(path):
    """
    Open `path` in the platform's default *text editor*.

    On macOS ``open -t`` forces the default text editor; on Linux there is no
    universal "edit" verb, so we fall back to ``xdg-open`` (which opens the
    user's default handler for the file type — for .md/.txt that is normally a
    text editor).
    """
    if sys.platform == "darwin":
        return _spawn(["open", "-t", path])
    if os.name == "nt":  # pragma: no cover - not the target platform
        return open_with_default_app(path)
    return _spawn(["xdg-open", path])


# Default file-manager reveal templates per platform. `{dir}` is the containing
# directory; `{file}` is the full path to the file itself. A configurable
# override (Config/Settings `file_manager`) may supply its own template.
_DEFAULT_FM_TEMPLATE = {
    "linux": "xdg-open {dir}",
    "darwin": "open -R {file}",
}


def reveal_in_file_manager(path, template=None):
    """
    Reveal `path` in the system file manager.

    If `template` is given it is a command string containing ``{dir}`` and/or
    ``{file}`` placeholders (honouring a configurable `file_manager` setting);
    otherwise a per-platform default is used. The template is split with shell
    lexing after substitution. Returns True on success.
    """
    directory = os.path.dirname(os.path.abspath(path))
    if template is None:
        if sys.platform == "darwin":
            template = _DEFAULT_FM_TEMPLATE["darwin"]
        elif os.name == "nt":  # pragma: no cover - not the target platform
            return _spawn(["explorer", os.path.normpath(directory)])
        else:
            template = _DEFAULT_FM_TEMPLATE["linux"]
    cmd = template.format(dir=shlex.quote(directory),
                          file=shlex.quote(os.path.abspath(path)))
    try:
        argv = shlex.split(cmd)
    except ValueError:
        return False
    if not argv:
        return False
    return _spawn(argv)


def uri_for_path(path):
    """
    Return a ``file://`` URI for a local path. Pure helper the front-ends can
    hand to a toolkit URI opener without importing GLib in the core.
    """
    from urllib.request import pathname2url
    return "file://" + pathname2url(os.path.abspath(path))
