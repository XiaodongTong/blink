from __future__ import annotations

from typing import TYPE_CHECKING

from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.layout import HSplit, VSplit, Layout, Window, ConditionalContainer
from prompt_toolkit.layout.controls import FormattedTextControl, UIContent, UIControl
from prompt_toolkit.layout.dimension import D
from prompt_toolkit.data_structures import Point
from prompt_toolkit.filters import Condition

from blink.tui.widgets.repo_list import RepoListWindow

if TYPE_CHECKING:
    from blink.tui.app import BlinkApp


class EditStatusControl(UIControl):
    def __init__(self, get_text, get_cursor_col):
        self._get_text = get_text
        self._get_cursor_col = get_cursor_col

    def is_focusable(self) -> bool:
        return True

    def create_content(self, width: int, height: int) -> UIContent:
        ft = self._get_text()
        show_cursor = False
        cursor_position = None
        col = self._get_cursor_col()
        if col is not None:
            show_cursor = True
            cursor_position = Point(x=col, y=0)

        def get_line(i: int):
            if i == 0:
                return ft
            return FormattedText([("", "")])

        return UIContent(
            get_line=get_line,
            line_count=1,
            show_cursor=show_cursor,
            cursor_position=cursor_position,
        )


NARROW_THRESHOLD = 80


def build_layout(app: BlinkApp) -> Layout:
    app._repo_list_window = RepoListWindow(app._repo_control)

    left_border = Condition(lambda: app._focus_pane == "list")
    right_border = Condition(lambda: app._focus_pane == "detail")
    detail_visible = Condition(
        lambda: app._detail_panel is not None and _is_wide_enough(app)
    )
    edit_active = Condition(lambda: app._in_edit_mode())
    search_filtering = Condition(
        lambda: app._search_filtering and not app._search_active
    )
    search_active = Condition(lambda: app._search_active)

    left_panel = HSplit([
        Window(height=D.exact(1), char="─",
               style=Condition(lambda: "class:border-focus" if left_border() else "class:border")),
        app._repo_list_window,
        Window(height=D.exact(1), char="─",
               style=Condition(lambda: "class:border-focus" if left_border() else "class:border")),
    ], width=D(min=25, preferred=48, max=70))

    right_panel = ConditionalContainer(
        HSplit([
            Window(height=D.exact(1), char="─",
                   style=Condition(lambda: "class:border-focus" if right_border() else "class:border")),
            app._detail_window,
            Window(height=D.exact(1), char="─",
                   style=Condition(lambda: "class:border-focus" if right_border() else "class:border")),
        ]),
        filter=detail_visible,
    )

    v_sep = ConditionalContainer(
        Window(char="│", style="class:border", width=D.exact(1)),
        filter=detail_visible,
    )

    main_area = VSplit([left_panel, v_sep, right_panel])

    edit_status = ConditionalContainer(
        app._edit_status_window,
        filter=edit_active,
    )
    regular_status = ConditionalContainer(
        Window(content=app._status_control, height=D.exact(1), style="class:status"),
        filter=Condition(lambda: not edit_active()),
    )

    return Layout(
        HSplit([
            ConditionalContainer(
                Window(
                    content=FormattedTextControl(text=app._search_prefix_text),
                    height=D.exact(1),
                    style="class:search-bar",
                ),
                filter=search_filtering,
            ),
            ConditionalContainer(
                HSplit([
                    Window(height=D.exact(1), char="─", style="class:search-border"),
                    app._search_bar.window,
                    Window(height=D.exact(1), char="─", style="class:search-border"),
                ]),
                filter=search_active,
            ),
            main_area,
            edit_status,
            regular_status,
            Window(content=app._footer_control, height=D.exact(1), style="class:footer"),
        ])
    )


def _is_wide_enough(app: BlinkApp) -> bool:
    try:
        cols = app._app.output.get_size().columns
        return cols >= NARROW_THRESHOLD
    except Exception:
        return True
