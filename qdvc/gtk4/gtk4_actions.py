"""
gtk4_actions.py — install the ``win.*`` Gio.SimpleActions for the GTK 4 window.

Per the common spec §9, every command in the GTK 4 front-end is a
``Gio.SimpleAction`` under the ``win.`` scope. Menu items and header buttons
reference actions by name, so one action drives every surface and
``action.set_enabled(bool)`` greys every bound item and its shortcut at once.
Accelerators are registered by the application (gtk4_app) from the shared
``ui_prefs.SHORTCUTS`` table.

This module is a mixin folded into the GTK 4 NotebookWindow. Each action maps to
an ``on_*`` handler defined on the window (in gtk4_window.py); the handlers reuse
the pure core exactly as the GTK 3 handlers do.
"""

from gi.repository import Gio, GLib


class ActionsMixin:
    """Installs and manages the window's Gio actions (see module docstring)."""

    def _install_actions(self):
        """Create every win.* action and connect it to its handler."""
        self._actions = {}

        # Simple (activate) actions: (name, handler).
        simple = [
            ("new-note", self.on_new_note),
            ("save-note", self.on_save_note),
            ("refresh-note", self.on_refresh_note),
            ("open-workspace", self.on_open_workspace),
            ("refresh-workspace", self.on_refresh_workspace),
            ("close-workspace", self.on_close_workspace),
            ("new-tab", self.on_new_tab),
            ("close-tab", self.on_close_tab),
            ("slugify", self.on_slugify),
            ("preferences", self.on_preferences),
            ("about", self.on_about),
            ("quit", self.on_quit),
            ("next-tab", self.on_next_tab),
            ("prev-tab", self.on_prev_tab),
        ]
        for name, handler in simple:
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", handler)
            self.add_action(act)
            self._actions[name] = act

        # Stateful (toggle) actions carrying a boolean state.
        toggles = [
            ("toggle-read-only", True, self.on_toggle_read_only),
            ("toggle-card-view", False, self.on_toggle_card_view),
            ("toggle-preview", False, self.on_toggle_preview),
            ("toggle-outline", False, self.on_toggle_outline),
        ]
        for name, default, handler in toggles:
            act = Gio.SimpleAction.new_stateful(
                name, None, GLib.Variant.new_boolean(default))
            act.connect("change-state", handler)
            self.add_action(act)
            self._actions[name] = act

        # goto-tab takes an integer parameter (Alt+1..9 → tab index).
        goto = Gio.SimpleAction.new(
            "goto-tab", GLib.VariantType.new("i"))
        goto.connect("activate", self.on_goto_tab)
        self.add_action(goto)
        self._actions["goto-tab"] = goto

        # open-recent takes a string parameter (the workspace folder path).
        open_recent = Gio.SimpleAction.new(
            "open-recent", GLib.VariantType.new("s"))
        open_recent.connect("activate", self.on_open_recent)
        self.add_action(open_recent)
        self._actions["open-recent"] = open_recent

        # Note context-menu actions. Each takes the note's path as a string
        # target so one action serves every row (spec §9 action model). The
        # move action's target is "src_path\ndest_path" (two paths, newline
        # separated) since a Gio action takes a single parameter.
        for name, handler in (
            ("note-open-new-tab", self.on_note_open_new_tab),
            ("note-slugify", self.on_note_slugify),
            ("note-copy-path", self.on_note_copy_path),
            ("note-show-in-files", self.on_note_show_in_files),
            ("note-move", self.on_note_move),
        ):
            act = Gio.SimpleAction.new(name, GLib.VariantType.new("s"))
            act.connect("activate", handler)
            self.add_action(act)
            self._actions[name] = act

    # --------------------------------------------------- helpers ------ #
    def _set_action_enabled(self, name, enabled):
        act = self._actions.get(name)
        if act is not None:
            act.set_enabled(bool(enabled))

    def _set_toggle_state(self, name, value):
        """Set a stateful action's boolean state without re-firing its handler
        loop (change-state handlers guard on the incoming value)."""
        act = self._actions.get(name)
        if act is not None:
            act.set_state(GLib.Variant.new_boolean(bool(value)))

    def _update_actions_sensitivity(self):
        """
        Centralised enable/disable logic (spec §8/§9 parity). Workspace-scoped
        actions require an open workspace; note-scoped actions require a note in
        the active tab; Save additionally requires unsaved changes; Slugify
        requires edit mode + a short H1 first line.
        """
        has_ws = self.root_folder is not None
        tab = self._active_view()
        has_note = bool(tab and tab.note)
        self._set_action_enabled("refresh-workspace", has_ws)
        self._set_action_enabled("close-workspace", has_ws)
        self._set_action_enabled("new-note", has_ws and not self.read_only)
        self._set_action_enabled("save-note",
                                 bool(has_note and tab and tab.dirty))
        self._set_action_enabled("refresh-note", has_note)
        self._set_action_enabled("close-tab", len(self._views) > 1)

        # Slugify: edit mode + active note whose live first line is a short H1.
        from .. import model
        slug_ok = False
        if has_note and not self.read_only and tab is not None:
            heading = model.heading_for_slug(tab.get_content())
            slug_ok = heading is not None and model.slugify(heading) != ""
        self._set_action_enabled("slugify", slug_ok)

        # Read-only cannot be toggled while previewing.
        self._set_action_enabled("toggle-read-only", not self.preview_mode)
