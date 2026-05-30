from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from blink.tui.status_bar import _build_ide_select_status, _build_horizontal_select


def _make_app(cursor=0, offset=0, width=120):
    app = MagicMock()
    app._ide_selecting = True
    app._ide_select_cursor = cursor
    app._ide_scroll_offset = offset
    app._ide_options.return_value = [
        ("v", "VSCode"),
        ("u", "Cursor"),
        ("a", "Antigravity"),
        ("i", "IntelliJ"),
        ("p", "PyCharm"),
        ("w", "WebStorm"),
        ("g", "GoLand"),
        ("s", "Sublime"),
        ("z", "Zed"),
        ("x", "Xcode"),
        ("n", "Neovim"),
        ("o", "System"),
    ]
    size = MagicMock()
    size.columns = width
    app._app.output.get_size.return_value = size
    return app


def _extract_text(ft):
    return "".join(text for _, text in ft)


def test_wide_terminal_shows_all():
    app = _make_app(cursor=0, offset=0, width=200)
    ft = _build_ide_select_status(app)
    text = _extract_text(ft)
    assert "VSCode" in text
    assert "System" in text
    assert "‹" not in text
    assert "›" not in text


def test_narrow_terminal_shows_scroll_right():
    app = _make_app(cursor=0, offset=0, width=80)
    ft = _build_ide_select_status(app)
    text = _extract_text(ft)
    assert "VSCode" in text
    assert "›" in text
    assert "System" not in text


def test_cursor_at_end_shows_scroll_left():
    app = _make_app(cursor=11, offset=0, width=80)
    ft = _build_ide_select_status(app)
    text = _extract_text(ft)
    assert "System" in text
    assert "‹" in text


def test_cursor_in_middle_shows_both_indicators():
    app = _make_app(cursor=5, offset=0, width=80)
    ft = _build_ide_select_status(app)
    text = _extract_text(ft)
    assert "WebStorm" in text
    assert "‹" in text
    assert "›" in text


def test_selected_item_has_arrow():
    app = _make_app(cursor=0, offset=0, width=200)
    ft = _build_ide_select_status(app)
    text = _extract_text(ft)
    assert "▸ VSCode" in text


def test_unselected_item_has_spaces():
    app = _make_app(cursor=0, offset=0, width=200)
    ft = _build_ide_select_status(app)
    text = _extract_text(ft)
    idx = text.index("Cursor")
    assert text[idx - 2:idx] == "  "


def test_scroll_offset_updated():
    app = _make_app(cursor=11, offset=0, width=80)
    _build_ide_select_status(app)
    assert app._ide_scroll_offset > 0


def test_cursor_visibility_after_scroll():
    app = _make_app(cursor=11, offset=0, width=80)
    ft = _build_ide_select_status(app)
    text = _extract_text(ft)
    assert "▸ System" in text


def test_terminal_resize_adapts():
    app = _make_app(cursor=11, offset=0, width=80)
    ft1 = _build_ide_select_status(app)
    offset_narrow = app._ide_scroll_offset

    app._app.output.get_size.return_value.columns = 200
    ft2 = _build_ide_select_status(app)
    text = _extract_text(ft2)
    assert "VSCode" in text
    assert "System" in text


def test_prefix_and_suffix_always_present():
    app = _make_app(cursor=0, offset=0, width=80)
    ft = _build_ide_select_status(app)
    text = _extract_text(ft)
    assert text.startswith(" Select IDE:  ")
    assert "←→:选择" in text


def test_very_narrow_terminal_shows_at_least_cursor():
    app = _make_app(cursor=5, offset=0, width=60)
    ft = _build_ide_select_status(app)
    text = _extract_text(ft)
    assert "WebStorm" in text


# ── _build_horizontal_select shared function tests ───────────────


def test_horizontal_select_model_options():
    ft, offset = _build_horizontal_select(
        opts=["haiku", "sonnet", "opus"],
        cursor=1, offset=0, width=200,
        prefix=" Select Model:  ",
        suffix="    ←→:选择  Enter:确认  Esc:取消",
    )
    text = _extract_text(ft)
    assert "haiku" in text
    assert "sonnet" in text
    assert "opus" in text
    assert "▸ sonnet" in text


def test_horizontal_select_model_all_visible():
    ft, offset = _build_horizontal_select(
        opts=["haiku", "sonnet", "opus"],
        cursor=0, offset=0, width=200,
        prefix=" Select Model:  ",
        suffix="    ←→:选择  Enter:确认  Esc:取消",
    )
    text = _extract_text(ft)
    assert "‹" not in text
    assert "›" not in text
