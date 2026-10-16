#!/usr/bin/env bash
# Build and install QDVC Markdown Notebook for the current user (no root needed).
#
#   scripts/build-app.sh               # check dependencies, run the tests, stage build/
#   scripts/build-app.sh --install     # ...and install to ~/.local (restarts a running copy)
#   scripts/build-app.sh --uninstall   # remove the installed copy
#   scripts/build-app.sh --no-tests    # skip the unit tests
#   scripts/build-app.sh --run         # after building/installing, start the app
#
# Installs:
#   ~/.local/share/qdvc-markdown-notebook/app/                  the program
#   ~/.local/bin/qdvc-markdown-notebook                         launcher script
#   ~/.local/share/applications/qdvc.MarkdownNotebook.desktop   menu entry (Activities, Dock)
#   ~/.local/share/icons/hicolor/.../qdvc.MarkdownNotebook*.svg app icons
# Set PREFIX to install elsewhere (default: ~/.local).
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
APP_ID="qdvc.MarkdownNotebook"
NAME="qdvc-markdown-notebook"
PREFIX="${PREFIX:-$HOME/.local}"
SHARE="$PREFIX/share"
APP_DIR="$SHARE/$NAME/app"
BIN_DIR="$PREFIX/bin"
DESKTOP="$SHARE/applications/$APP_ID.desktop"
# The launcher name used by older builds and by the README's old hand-written
# instructions; replaced by $DESKTOP (named after the application id, which is
# what GNOME Shell on Wayland matches windows against).
LEGACY_DESKTOP="$SHARE/applications/$NAME.desktop"
ICONS="$SHARE/icons/hicolor"
STAGE="$ROOT/build/$NAME"

install=0 uninstall=0 tests=1 run=0
for arg in "$@"; do
    case "$arg" in
        --install) install=1 ;;
        --uninstall) uninstall=1 ;;
        --no-tests) tests=0 ;;
        --run) run=1 ;;
        -h|--help) sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $arg (see --help)" >&2; exit 2 ;;
    esac
done

say() { printf '==> %s\n' "$*"; }

# Is a copy running? Ask it to quit through its D-Bus app.quit action, which
# goes through the window's own Quit (unsaved-changes prompt, session save).
running() {
    command -v gdbus >/dev/null 2>&1 || return 1
    gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus \
        --method org.freedesktop.DBus.NameHasOwner "$APP_ID" 2>/dev/null | grep -q true
}
quit_running() {
    gdbus call --session --dest "$APP_ID" --object-path "/${APP_ID//./\/}" \
        --method org.gtk.Actions.Activate quit [] {} >/dev/null 2>&1 || true
    for _ in $(seq 1 50); do running || return 0; sleep 0.1; done
    echo "note: the running copy is still open (unsaved changes?); close it to use the new version" >&2
    return 1
}

refresh_caches() {
    command -v update-desktop-database >/dev/null 2>&1 \
        && update-desktop-database -q "$SHARE/applications" 2>/dev/null || true
    touch "$ICONS" "$SHARE/applications" 2>/dev/null || true
    command -v gtk4-update-icon-cache >/dev/null 2>&1 \
        && gtk4-update-icon-cache -q -t -f "$ICONS" 2>/dev/null \
        || { command -v gtk-update-icon-cache >/dev/null 2>&1 \
             && gtk-update-icon-cache -q -t -f "$ICONS" 2>/dev/null; } || true
}

if [[ $uninstall -eq 1 ]]; then
    running && { say "Quitting the running copy"; quit_running || true; }
    rm -rf "$SHARE/$NAME" "$BIN_DIR/$NAME" "$DESKTOP" \
        "$ICONS/scalable/apps/$APP_ID.svg" "$ICONS/symbolic/apps/$APP_ID-symbolic.svg"
    refresh_caches
    say "Uninstalled (your notes and ~/.config/$NAME are untouched)"
    exit 0
fi

# --- dependencies ---------------------------------------------------------
# The app has two front-ends (GTK 3, the default, and GTK 4 / libadwaita) and
# needs at least one; it falls back to GTK 3 when GTK 4 is unavailable.
say "Checking dependencies"
if ! python3 - <<'PY'
import subprocess
import sys

problems, notes = [], []
if sys.version_info < (3, 10):
    problems.append("Python 3.10 or later")


def probe(code):
    """Run a check in a fresh interpreter: GTK 3 and GTK 4 can't share one."""
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    out = r.stdout.strip() or (r.stderr.strip().splitlines() or [""])[-1]
    return r.returncode == 0, out


ok3, info3 = probe(
    "import gi; gi.require_version('Gtk', '3.0'); from gi.repository import Gtk; "
    "print('GTK %d.%d.%d' % (Gtk.get_major_version(), Gtk.get_minor_version(), "
    "Gtk.get_micro_version()))")
ok4, info4 = probe(
    "import gi; gi.require_version('Gtk', '4.0'); gi.require_version('Adw', '1'); "
    "from gi.repository import Gtk, Adw; "
    "v = (Adw.get_major_version(), Adw.get_minor_version()); "
    "assert v >= (1, 4), 'libadwaita 1.4 or later needed (found %d.%d)' % v; "
    "print('GTK %d.%d.%d, libadwaita %d.%d.%d' % (Gtk.get_major_version(), "
    "Gtk.get_minor_version(), Gtk.get_micro_version(), Adw.get_major_version(), "
    "Adw.get_minor_version(), Adw.get_micro_version()))")
print("    GTK 3 front-end:", info3 if ok3 else f"not available ({info3})")
print("    GTK 4 front-end:", info4 if ok4 else f"not available ({info4})")
print("    Python", sys.version.split()[0])
if not (ok3 or ok4):
    problems.append("PyGObject with GTK 3, or with GTK 4 and libadwaita 1.4+")
if ok3:
    ok_cairo, _ = probe("import gi; gi.require_foreign('cairo')")
    if not ok_cairo:
        notes.append("PyGObject's cairo support is missing: the GTK 3 front-end "
                     "shades fenced code instead of drawing a box around it")
try:
    import yaml  # noqa: F401
except ImportError:
    notes.append("PyYAML is missing: the app runs, but saves no preferences")
for n in notes:
    print("note: " + n, file=sys.stderr)
if problems:
    print("Missing: " + "; ".join(problems), file=sys.stderr)
    sys.exit(1)
PY
then
    cat >&2 <<'HELP'
Install the dependencies, then run this script again:
  Debian/Ubuntu: sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-gtk-4.0 gir1.2-adw-1 python3-yaml
  Fedora:        sudo dnf install python3-gobject python3-cairo gtk3 gtk4 libadwaita python3-pyyaml
  Arch:          sudo pacman -S python-gobject python-cairo gtk3 gtk4 libadwaita python-yaml
HELP
    exit 1
fi

# --- tests and build ------------------------------------------------------
if [[ $tests -eq 1 ]]; then
    say "Running the tests"
    if ! python3 -m unittest discover -s tests -t . -q; then
        echo "Tests failed; nothing was installed." >&2
        exit 1
    fi
fi

say "Staging $STAGE"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp qdvc_markdown_notebook.py "$STAGE/"
cp -r qdvc data "$STAGE/"
rm -f "$STAGE/data/"*.desktop.in
find "$STAGE" -name '__pycache__' -prune -exec rm -rf {} +
python3 -m compileall -q "$STAGE" >/dev/null

if [[ $install -eq 1 ]]; then
    was_running=0
    if running; then
        say "Quitting the running copy (it asks about unsaved changes first)"
        quit_running && was_running=1 || true
    fi
    say "Installing to $PREFIX"
    rm -rf "$APP_DIR"
    mkdir -p "$APP_DIR" "$BIN_DIR" "$SHARE/applications" \
        "$ICONS/scalable/apps" "$ICONS/symbolic/apps"
    cp -r "$STAGE/." "$APP_DIR/"
    cat > "$BIN_DIR/$NAME" <<LAUNCHER
#!/bin/sh
exec python3 "$APP_DIR/qdvc_markdown_notebook.py" "\$@"
LAUNCHER
    chmod +x "$BIN_DIR/$NAME"
    sed "s|@BINDIR@|$BIN_DIR|g" "data/$APP_ID.desktop.in" > "$DESKTOP"
    if [[ -f "$LEGACY_DESKTOP" ]]; then
        rm -f "$LEGACY_DESKTOP"
        say "Removed the old launcher $LEGACY_DESKTOP (replaced by $APP_ID.desktop)"
    fi
    cp "data/icons/hicolor/scalable/apps/$APP_ID.svg" "$ICONS/scalable/apps/"
    cp "data/icons/hicolor/symbolic/apps/$APP_ID-symbolic.svg" "$ICONS/symbolic/apps/"
    if command -v desktop-file-validate >/dev/null 2>&1; then
        desktop-file-validate "$DESKTOP" || echo "warning: desktop-file-validate complained" >&2
    fi
    refresh_caches
    say "Installed: open QDVC Markdown Notebook from Activities, or run $NAME"
    case ":$PATH:" in *":$BIN_DIR:"*) ;; *) echo "note: $BIN_DIR is not on your PATH" >&2 ;; esac
    if [[ $was_running -eq 1 ]]; then run=1; fi
fi

if [[ $run -eq 1 ]]; then
    if [[ $install -eq 1 ]]; then cmd=("$BIN_DIR/$NAME"); else cmd=(python3 "$STAGE/qdvc_markdown_notebook.py"); fi
    say "Starting QDVC Markdown Notebook"
    nohup "${cmd[@]}" >/dev/null 2>&1 &
fi
say "Done"
