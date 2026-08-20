"""测试用的内存假平台与控件树构造工具。"""
from __future__ import annotations

import pytest

from desktop_pilot.core.element import ControlType, Element, Window
from desktop_pilot.core.platform import Platform
from desktop_pilot.core.types import Rect


class FakePlatform(Platform):
    """记录调用、用内存控件树驱动的假后端。"""

    def __init__(self, windows=None, screenshot_png: bytes | None = None) -> None:
        self._windows = windows or []
        self._png = screenshot_png or b"\x89PNG_FAKE"
        self.calls: list[tuple[str, tuple]] = []
        self.typed: list[str] = []
        self.keys: list[str] = []
        self.clicks: list[tuple[int, int]] = []
        self.scrolls: list[tuple] = []
        self.closed = False
        # 测试用：list_elements 抛异常的开关
        self.fail_elements = False

    # 感知
    def screenshot(self) -> bytes:
        self.calls.append(("screenshot", ()))
        return self._png

    def list_windows(self):
        self.calls.append(("list_windows", ()))
        return list(self._windows)

    def find_window(self, title=None, title_contains=None, pid=None):
        self.calls.append(("find_window", (title, title_contains, pid)))
        for w in self._windows:
            if title is not None and w.name != title:
                continue
            if title_contains is not None and title_contains not in (w.name or ""):
                continue
            if pid is not None and w.pid != pid:
                continue
            return w
        from desktop_pilot.core.exceptions import WindowNotFoundError

        raise WindowNotFoundError("not found")

    def list_elements(self, window):
        self.calls.append(("list_elements", (window,)))
        if self.fail_elements:
            raise RuntimeError("boom")
        return list(getattr(window, "_roots", []))

    # 输入
    def move_to(self, x, y):
        self.calls.append(("move_to", (x, y)))

    def click(self, x, y):
        self.clicks.append((x, y))
        self.calls.append(("click", (x, y)))

    def double_click(self, x, y):
        self.calls.append(("double_click", (x, y)))

    def right_click(self, x, y):
        self.calls.append(("right_click", (x, y)))

    def middle_click(self, x, y):
        self.calls.append(("middle_click", (x, y)))

    def mouse_down(self, button="left", x=None, y=None):
        self.calls.append(("mouse_down", (button, x, y)))

    def mouse_up(self, button="left", x=None, y=None):
        self.calls.append(("mouse_up", (button, x, y)))

    def type_text(self, text):
        self.typed.append(text)
        self.calls.append(("type_text", (text,)))

    def key_press(self, key):
        self.keys.append(key)
        self.calls.append(("key_press", (key,)))

    def scroll(self, direction, amount=3, x=None, y=None):
        self.scrolls.append((direction, amount, x, y))
        self.calls.append(("scroll", (direction, amount, x, y)))

    def drag(self, x1, y1, x2, y2):
        self.calls.append(("drag", (x1, y1, x2, y2)))

    def close(self):
        self.closed = True


def make_window(title: str = "测试窗口", hwnd: int = 1000, pid: int = 42) -> Window:
    return Window(
        name=title,
        control_type=ControlType.WINDOW,
        rect=Rect(0, 0, 800, 600),
        hwnd=hwnd,
        pid=pid,
        handle=hwnd,
    )


def make_button(name: str, rect: Rect, parent: Element | None = None) -> Element:
    el = Element(
        name=name,
        control_type=ControlType.BUTTON,
        rect=rect,
        handle=f"btn:{name}",
    )
    el.parent = parent
    return el


def make_edit(name: str, rect: Rect, value: str = "") -> Element:
    return Element(
        name=name,
        control_type=ControlType.EDIT,
        rect=rect,
        value=value,
        handle=f"edit:{name}",
    )


def make_text(name: str, rect: Rect) -> Element:
    return Element(
        name=name, control_type=ControlType.TEXT, rect=rect, handle=f"txt:{name}"
    )


def attach_roots(window: Window, roots: list[Element]) -> Window:
    """把控件树挂到 window 上（FakePlatform.list_elements 读取 _roots）。"""
    window._roots = roots  # type: ignore[attr-defined]
    for r in roots:
        r.parent = window
    return window


@pytest.fixture
def fake_platform():
    return FakePlatform()
