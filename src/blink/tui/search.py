from __future__ import annotations

from typing import Callable

from prompt_toolkit.buffer import Buffer
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import BufferControl
from prompt_toolkit.layout.dimension import D


class SearchBar:
    def __init__(self, on_change: Callable[[str], None] | None = None) -> None:
        self._on_change = on_change
        self.buffer = Buffer(
            multiline=False,
            on_text_changed=self._text_changed,
        )
        self.control = BufferControl(buffer=self.buffer, focusable=True)
        self.window = Window(
            content=self.control,
            height=D.exact(1),
            style="class:search-input",
        )

    def _text_changed(self, buf: Buffer) -> None:
        if self._on_change:
            self._on_change(buf.text)

    @property
    def text(self) -> str:
        return self.buffer.text

    def clear(self) -> None:
        self.buffer.text = ""

    def focus(self, app) -> None:
        app.layout.focus(self.window)
