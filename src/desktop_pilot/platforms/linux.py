"""Linux 后端占位实现。

接口对齐，但每个方法都抛 :class:`UnsupportedOperationError`。
未来可基于 AT-SPI2（pyatspi）+ python-xlib / pynput 实现。
"""
from __future__ import annotations

from ..core.element import Element, Window
from ..core.exceptions import UnsupportedOperationError
from ..core.platform import Platform

_MSG = "Linux 后端暂未实现，欢迎贡献（建议基于 AT-SPI2 + python-xlib）"


class LinuxPlatform(Platform):
    """Linux 占位后端，所有操作均未实现。"""

    def _unsupported(self) -> UnsupportedOperationError:
        return UnsupportedOperationError(_MSG)

    def screenshot(self) -> bytes:
        raise self._unsupported()

    def list_windows(self) -> list[Window]:
        raise self._unsupported()

    def find_window(
        self,
        title: str | None = None,
        title_contains: str | None = None,
        pid: int | None = None,
    ) -> Window:
        raise self._unsupported()

    def list_elements(self, window: Window) -> list[Element]:
        raise self._unsupported()

    def click(self, x: int, y: int) -> None:
        raise self._unsupported()

    def double_click(self, x: int, y: int) -> None:
        raise self._unsupported()

    def right_click(self, x: int, y: int) -> None:
        raise self._unsupported()

    def type_text(self, text: str) -> None:
        raise self._unsupported()

    def key_press(self, key: str) -> None:
        raise self._unsupported()

    def scroll(self, direction: str, amount: int = 3) -> None:
        raise self._unsupported()

    def drag(self, x1: int, y1: int, x2: int, y2: int) -> None:
        raise self._unsupported()

    def close(self) -> None:
        return None
