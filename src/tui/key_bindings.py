from __future__ import annotations

from typing import TYPE_CHECKING

from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.filters import Condition

if TYPE_CHECKING:
    from blink.tui.app import BlinkApp


def build_key_bindings(app: BlinkApp) -> KeyBindings:
    kb = KeyBindings()

    not_searching = Condition(lambda: not app._search_active)
    not_editing = Condition(lambda: not app._in_edit_mode())
    not_ide_selecting = Condition(lambda: not app._ide_selecting)

    # ── IDE selection mode (highest priority) ───────────────────────────

    @kb.add("left", filter=Condition(lambda: app._ide_selecting))
    def _(event):
        app._ide_select_cursor = max(0, app._ide_select_cursor - 1)
        app._app.invalidate()

    @kb.add("right", filter=Condition(lambda: app._ide_selecting))
    def _(event):
        opts = app._ide_options()
        app._ide_select_cursor = min(len(opts) - 1, app._ide_select_cursor + 1)
        app._app.invalidate()

    @kb.add("enter", eager=True, filter=Condition(lambda: app._ide_selecting))
    def _(event):
        opts = app._ide_options()
        if opts and 0 <= app._ide_select_cursor < len(opts):
            key, name = opts[app._ide_select_cursor]
            app._config.set("editor", name)
            app._ide_selecting = False
            path = app._ide_pending_path
            app._ide_pending_path = None
            if path:
                from blink.tui.actions import open_in_editor
                open_in_editor(path, key, app._editors)
                app._set_scan_status(f"正在打开 {name}...")
            else:
                app._app.invalidate()
        return

    @kb.add("escape", eager=True, filter=Condition(lambda: app._ide_selecting))
    def _(event):
        app._ide_selecting = False
        app._ide_pending_path = None
        app._app.invalidate()
        return

    @kb.add("c-c", eager=True, filter=Condition(lambda: app._ide_selecting))
    def _(event):
        app._ide_selecting = False
        app._ide_pending_path = None
        app._app.invalidate()
        return

    # ── Config selection mode (highest priority, eager) ────────────────

    @kb.add("left", eager=True, filter=Condition(lambda: app._config_selecting))
    def _(event):
        if app._config_panel:
            opts = app._config_panel.get_select_options()
            app._config_panel.select_cursor = max(0, app._config_panel.select_cursor - 1)
            app._app.invalidate()

    @kb.add("right", eager=True, filter=Condition(lambda: app._config_selecting))
    def _(event):
        if app._config_panel:
            opts = app._config_panel.get_select_options()
            if opts:
                app._config_panel.select_cursor = min(len(opts) - 1, app._config_panel.select_cursor + 1)
            app._app.invalidate()

    @kb.add("enter", eager=True, filter=Condition(lambda: app._config_selecting))
    def _(event):
        if app._config_panel:
            app._config_panel.confirm_selection()
            app._config_selecting = False
            app._app.invalidate()
        return

    @kb.add("escape", eager=True, filter=Condition(lambda: app._config_selecting))
    def _(event):
        if app._config_panel:
            app._config_panel.cancel_selection()
        app._config_selecting = False
        app._app.invalidate()
        return

    @kb.add("c-c", eager=True, filter=Condition(lambda: app._config_selecting))
    def _(event):
        if app._config_panel:
            app._config_panel.cancel_selection()
        app._config_selecting = False
        app._app.invalidate()
        return

    # ── Review branch selection mode ───────────────────────────────────

    @kb.add("left", filter=Condition(lambda: app._review.selecting))
    def _(event):
        app._review.branch_cursor = max(0, app._review.branch_cursor - 1)
        app._app.invalidate()

    @kb.add("right", filter=Condition(lambda: app._review.selecting))
    def _(event):
        n = len(app._review.branches)
        app._review.branch_cursor = min(n - 1, app._review.branch_cursor + 1)
        app._app.invalidate()

    @kb.add("enter", eager=True, filter=Condition(lambda: app._review.selecting))
    def _(event):
        app._confirm_review_branch()
        return

    # ── Ctrl+C ──────────────────────────────────────────────────────────

    @kb.add("c-c")
    def _(event):
        if app._ide_selecting:
            return
        if app._config_selecting:
            if app._config_panel:
                app._config_panel.cancel_selection()
            app._config_selecting = False
            app._app.invalidate()
            return
        if app._review.selecting or app._review.branch_loading:
            app._cancel_review()
            return
        if app._in_edit_mode():
            app._cancel_edit()
            return
        if app._search_active:
            app._cancel_search()
            return
        if app._search_filtering:
            app._cancel_search()
            return
        import time
        now = time.monotonic()
        if app._ctrl_c_quit_hint and (now - app._last_ctrl_c) < 2.0:
            event.app.exit()
            return
        app._last_ctrl_c = now
        app._ctrl_c_quit_hint = True
        app._app.invalidate()
        app._start_timer(2.0, app._reset_ctrl_c_hint)

    # ── Escape ───────────────────────────────────────────────────────────

    @kb.add("escape")
    def _(event):
        if app._ide_selecting:
            return
        if app._config_selecting:
            if app._config_panel:
                app._config_panel.cancel_selection()
            app._config_selecting = False
            app._app.invalidate()
            return
        if app._review.selecting or app._review.branch_loading:
            app._cancel_review()
            return
        if app._in_edit_mode():
            app._cancel_edit()
            return
        if app._search_active:
            app._cancel_search()
            return
        if app._search_filtering:
            app._cancel_search()
            return
        if app._focus_pane == "config":
            app._exit_config()
            return
        if app._focus_pane == "detail":
            app._set_focus("list")
            app._app.layout.focus(app._repo_list_window)
            app._app.invalidate()

    # ── Focus switching: Tab/→ → detail, ← → list ────────────────────

    @kb.add(Keys.Tab, filter=Condition(
        lambda: not app._search_active and not app._in_edit_mode() and not app._ide_selecting
        and app._focus_pane != "config"))
    def _(event):
        if app._detail_panel is not None and app._focus_pane == "list":
            app._set_focus("detail")
            app._detail_panel.set_repo(app._repo_control.selected_repo())
            app._app.layout.focus(app._detail_window)
            app._app.invalidate()

    @kb.add("right", filter=Condition(
        lambda: not app._search_active and not app._in_edit_mode()
        and not app._ide_selecting and app._focus_pane == "list"))
    def _(event):
        if app._detail_panel is not None:
            app._set_focus("detail")
            app._detail_panel.set_repo(app._repo_control.selected_repo())
            app._app.layout.focus(app._detail_window)
            app._app.invalidate()

    @kb.add("left", filter=Condition(
        lambda: not app._search_active and not app._in_edit_mode()
        and not app._ide_selecting and app._focus_pane == "detail"))
    def _(event):
        app._set_focus("list")
        app._app.layout.focus(app._repo_list_window)
        app._app.invalidate()

    # ── Arrow keys — confirm search on down ────────────────────────────

    @kb.add("down", filter=Condition(lambda: app._search_active))
    @kb.add("s-down", filter=Condition(lambda: app._search_active))
    def _(event):
        app._search_active = False
        if app._search_bar.text:
            app._search_filtering = True
        app._set_focus("list")
        app._app.layout.focus(app._repo_list_window)
        app._repo_control.move_down()
        app._sync_detail_panel()
        app._app.invalidate()
        return

    # ── Arrow keys — list view navigation ───────────────────────────────

    @kb.add("down", filter=Condition(
        lambda: not app._search_active and app._focus_pane == "list" and not app._ide_selecting))
    @kb.add("s-down", filter=Condition(
        lambda: not app._search_active and app._focus_pane == "list" and not app._ide_selecting))
    def _(event):
        app._repo_control.move_down()
        app._sync_detail_panel()
        app._app.invalidate()

    @kb.add("up", filter=Condition(
        lambda: not app._search_active and app._focus_pane == "list" and not app._ide_selecting))
    @kb.add("s-up", filter=Condition(
        lambda: not app._search_active and app._focus_pane == "list" and not app._ide_selecting))
    def _(event):
        app._repo_control.move_up()
        app._sync_detail_panel()
        app._app.invalidate()

    # ── Arrow keys — detail view line navigation ──────────────────────────

    @kb.add("down", filter=Condition(
        lambda: app._focus_pane == "detail" and not app._search_active
        and not app._ide_selecting and not app._in_edit_mode()))
    def _(event):
        if app._detail_panel:
            app._detail_panel.cursor_down()
            app._app.invalidate()

    @kb.add("up", filter=Condition(
        lambda: app._focus_pane == "detail" and not app._search_active
        and not app._ide_selecting and not app._in_edit_mode()))
    def _(event):
        if app._detail_panel:
            app._detail_panel.cursor_up()
            app._app.invalidate()

    # ── Shift+Arrow — group jump in detail view ──────────────────────

    @kb.add("s-down", filter=Condition(
        lambda: app._focus_pane == "detail" and not app._search_active
        and not app._ide_selecting and not app._in_edit_mode()))
    def _(event):
        if app._detail_panel:
            app._detail_panel.cursor_group_down()
            app._app.invalidate()

    @kb.add("s-up", filter=Condition(
        lambda: app._focus_pane == "detail" and not app._search_active
        and not app._ide_selecting and not app._in_edit_mode()))
    def _(event):
        if app._detail_panel:
            app._detail_panel.cursor_group_up()
            app._app.invalidate()

    # ── Config panel navigation ─────────────────────────────────────────

    @kb.add("down", filter=Condition(
        lambda: app._focus_pane == "config" and not app._config_selecting))
    def _(event):
        if app._config_panel:
            app._config_panel.cursor_down()
            app._app.invalidate()

    @kb.add("up", filter=Condition(
        lambda: app._focus_pane == "config" and not app._config_selecting))
    def _(event):
        if app._config_panel:
            app._config_panel.cursor_up()
            app._app.invalidate()

    @kb.add("enter", filter=Condition(
        lambda: app._focus_pane == "config" and not app._config_selecting))
    def _(event):
        if app._config_panel:
            from blink.tui.app_config import ConfigSelectMode, _EDITABLE_ITEMS
            idx = app._config_panel._cursor
            if idx < len(_EDITABLE_ITEMS):
                _, _, itype = _EDITABLE_ITEMS[idx]
                if itype == "editor":
                    app._config_panel.select_mode = ConfigSelectMode.editor
                else:
                    app._config_panel.select_mode = ConfigSelectMode.model
                app._config_selecting = True
                app._app.invalidate()
        return

    # ── e — open config.json in editor ──────────────────────────────────

    @kb.add("e", filter=Condition(
        lambda: app._focus_pane == "config" and not app._config_selecting))
    def _(event):
        app._open_config_in_editor()

    # ── Shift+S — enter config panel ──────────────────────────────────

    @kb.add("S", filter=Condition(
        lambda: not app._search_active and not app._in_edit_mode()
        and not app._ide_selecting and not app._review.selecting
        and not app._review.branch_loading and not app._config_selecting
        and app._focus_pane != "config"))
    def _(event):
        app._enter_config()

    # ── Search (available from both panes) ───────────────────────────────

    @kb.add("/", filter=Condition(lambda: not app._search_active and not app._in_edit_mode()))
    def _(event):
        app._search_active = True
        app._search_filtering = False
        app._search_bar.clear()
        app._search_bar.focus(event.app)
        app._app.invalidate()

    # ── Shift+1 (!) — open terminal ──────────────────────────────────

    @kb.add("!", filter=Condition(
        lambda: not app._search_active and not app._in_edit_mode()
        and not app._ide_selecting and app._focus_pane != "config"))
    def _(event):
        app._trigger_footer_highlight()
        app._open_terminal()

    # ── Shift+2 (@) — open with preferred IDE ──────────────────────────

    @kb.add("@", filter=Condition(
        lambda: not app._search_active and not app._in_edit_mode()
        and not app._ide_selecting and app._focus_pane != "config"))
    def _(event):
        app._trigger_footer_highlight()
        repo = app._get_active_repo()
        if repo:
            app._trigger_open_ide(repo)

    # ── Shift+3 (#) — open in Finder ─────────────────────────────────

    @kb.add("#", filter=Condition(
        lambda: not app._search_active and not app._in_edit_mode()
        and not app._ide_selecting and app._focus_pane != "config"))
    def _(event):
        app._trigger_footer_highlight()
        repo = app._get_active_repo()
        if repo:
            from blink.tui.actions import open_in_editor
            open_in_editor(repo.path, "o", app._editors)

    # ── Shift+4 ($) — open in browser ────────────────────────────────

    @kb.add("$", filter=Condition(
        lambda: not app._search_active and not app._in_edit_mode()
        and not app._ide_selecting and app._focus_pane != "config"))
    def _(event):
        app._trigger_footer_highlight()
        app._open_git_in_browser()

    # ── Shift+5 (%) — push changes ────────────────────────────────────

    @kb.add("%", filter=Condition(
        lambda: not app._search_active and not app._in_edit_mode()
        and not app._ide_selecting and app._focus_pane != "config"))
    def _(event):
        app._trigger_footer_highlight()
        repo = app._get_active_repo()
        if repo:
            app._run_commit(repo)

    # ── Shift+6 (^) — pull changes ────────────────────────────────────

    @kb.add("^", filter=Condition(
        lambda: not app._search_active and not app._in_edit_mode()
        and not app._ide_selecting and app._focus_pane != "config"))
    def _(event):
        app._trigger_footer_highlight()
        repo = app._get_active_repo()
        if repo:
            app._run_pull(repo)

    # ── Shift+7 (&) — add todo task ──────────────────────────────────

    @kb.add("&", filter=Condition(
        lambda: not app._search_active and not app._in_edit_mode()
        and not app._ide_selecting and app._focus_pane != "config"))
    def _(event):
        app._trigger_footer_highlight()
        app._run_add_task()

    # ── Shift+8 (*) — start review ────────────────────────────────────

    @kb.add("*", filter=Condition(
        lambda: not app._search_active and not app._in_edit_mode()
        and not app._ide_selecting and app._focus_pane != "config"))
    def _(event):
        app._trigger_footer_highlight()
        repo = app._get_active_repo()
        if repo:
            app._start_review_branch_select()

    # ── Shift+R — rescan ─────────────────────────────────────────────

    @kb.add("R", filter=Condition(
        lambda: not app._search_active and not app._in_edit_mode()
        and not app._ide_selecting and app._focus_pane != "config"))
    def _(event):
        app._trigger_footer_highlight()
        if not app._scanning:
            app._start_background_scan()

    # ── Shift+L — open last review report ─────────────────────────

    @kb.add("L", filter=Condition(
        lambda: not app._search_active and not app._in_edit_mode()
        and not app._ide_selecting and app._focus_pane != "config"))
    def _(event):
        app._trigger_footer_highlight()
        repo = app._get_active_repo()
        if repo and repo.path in app._review.last_report_paths:
            app._open_with_ide(app._review.last_report_paths[repo.path])

    # ── Enter ────────────────────────────────────────────────────────────

    @kb.add("enter")
    def _(event):
        if app._ide_selecting:
            return
        if app._config_selecting:
            return
        if app._review.selecting:
            app._confirm_review_branch()
            return
        if app._search_active:
            app._search_active = False
            if app._search_bar.text:
                app._search_filtering = True
            app._set_focus("list")
            app._app.layout.focus(app._repo_list_window)
            app._app.invalidate()
            return
        if app._focus_pane == "config":
            return
        if app._focus_pane in ("detail", "edit") and app._detail_panel is not None:
            app._detail_panel.handle_enter()
            if app._detail_panel.is_editing:
                app._set_focus("edit")
                app._app.layout.focus(app._edit_status_window)
            else:
                app._set_focus("detail")
                app._app.layout.focus(app._detail_window)
            app._app.invalidate()
            return
        if app._focus_pane == "list":
            repo = app._repo_control.selected_repo()
            if repo:
                app._trigger_open_ide(repo)

    # ── Tag removal 1-9 (detail panel tag edit mode) ────────────────────

    for i in range(1, 10):
        def make_tag_remove(n):
            def _(event):
                if app._detail_panel is not None and app._detail_panel.edit_mode == "tags":
                    app._detail_panel.handle_key(str(n))
                    app._app.invalidate()
            return _
        kb.add(str(i), filter=Condition(lambda: not app._search_active))(make_tag_remove(i))

    # ── Backspace — route to active buffer in any edit mode ──────────────

    @kb.add("backspace", eager=True, filter=Condition(lambda: app._in_edit_mode()))
    def _(event):
        app._route_backspace()

    # ── Printable chars — route to active buffer in any edit mode ────────

    for code in range(33, 127):
        char = chr(code)
        if char.isdigit():
            continue
        def make_handler(c):
            def _(event):
                app._route_printable(c)
            return _
        kb.add(char, eager=True, filter=Condition(lambda: app._in_edit_mode()))(make_handler(char))

    # ── Space — route to active buffer ───────────────────────────────────

    @kb.add("space", eager=True, filter=Condition(lambda: app._in_edit_mode()))
    def _(event):
        app._route_printable(" ")

    # ── Non-ASCII printable (CJK etc.) ────────────────────────────────────

    @kb.add(Keys.Any, filter=Condition(lambda: app._in_edit_mode()))
    def _(event):
        key_seq = event.key_sequence
        if key_seq and len(key_seq) == 1:
            k = key_seq[0].key
            if isinstance(k, str) and k.isprintable() and len(k) == 1 and ord(k) > 127:
                app._route_printable(k)

    # ── Digits 0-9 — route to buffer only when NOT in tag mode ─────────────

    for d in "0123456789":
        def make_handler(c):
            def _(event):
                app._route_printable(c)
            return _
        kb.add(d, eager=True, filter=Condition(
            lambda: app._in_edit_mode() and not app._in_tag_mode()))(
            make_handler(d)
        )

    return kb
