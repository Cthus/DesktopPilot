"""DesktopPilot — 给 AI agent 用的 Windows 桌面图形化编程 SDK。

Example:
    >>> from desktop_pilot import Desktop
    >>> with Desktop() as bot:
    ...     win = bot.find_window(title_contains="微信")
    ...     bot.click_button(window=win, name="发送")

公开了底层 :class:`Platform` 方法（截图、列窗口、坐标点击、按键……）以及
agent 友好的高层语义动作（按名字点按钮、按标签填输入框、等元素出现、批量填表）。
"""
from __future__ import annotations

import sys
from typing import Optional

from .core.element import Control, ControlType, Element, Window
from .core.exceptions import (
    DesktopPilotError,
    ElementNotFoundError,
    PlatformError,
    UnsupportedOperationError,
    WaitTimeoutError,
    WindowNotFoundError,
)
from .core.platform import Platform
from .core.types import Point, Rect, Size

__version__ = "0.3.0"

__all__ = [
    "Desktop",
    "Platform",
    # 元素模型
    "Element",
    "Control",
    "Window",
    "ControlType",
    # 几何类型
    "Point",
    "Size",
    "Rect",
    # 异常
    "DesktopPilotError",
    "ElementNotFoundError",
    "WindowNotFoundError",
    "WaitTimeoutError",
    "PlatformError",
    "UnsupportedOperationError",
    "__version__",
]


class Desktop:
    """桌面自动化入口。

    - 自动检测当前平台，lazy 加载对应后端。
    - 可作为 context manager 使用（``with Desktop() as bot:``）。
    - 底层后端方法通过代理直接暴露；高层语义动作以方法形式提供。
    """

    def __init__(self, platform: Optional[Platform] = None) -> None:
        if platform is not None:
            self._platform = platform
            self._platform_name = platform.__class__.__name__
        else:
            self._platform = self._detect_platform()
            self._platform_name = sys.platform

    @staticmethod
    def _detect_platform() -> Platform:
        if sys.platform == "win32":
            from .platforms.windows import WindowsPlatform

            return WindowsPlatform()
        elif sys.platform == "darwin":
            from .platforms.macos import MacOSPlatform

            return MacOSPlatform()
        else:
            from .platforms.linux import LinuxPlatform

            return LinuxPlatform()

    @property
    def platform(self) -> Platform:
        """返回底层平台后端（高级/集成层有时需要直接传 platform 给 action 函数）。"""
        return self._platform

    # ------------------------------------------------------------------ #
    # 感知（直接代理给平台）
    # ------------------------------------------------------------------ #
    def screenshot(self) -> bytes:
        """截取全屏，返回 PNG 字节。"""
        return self._platform.screenshot()

    def list_windows(self) -> list[Window]:
        return self._platform.list_windows()

    def find_window(
        self,
        title: Optional[str] = None,
        title_contains: Optional[str] = None,
        pid: Optional[int] = None,
    ) -> Window:
        return self._platform.find_window(
            title=title, title_contains=title_contains, pid=pid
        )

    def list_elements(self, window: Window) -> list[Element]:
        return self._platform.list_elements(window)

    # ------------------------------------------------------------------ #
    # 基础输入：鼠标
    # ------------------------------------------------------------------ #
    def move_to(self, x: int, y: int) -> None:
        """把鼠标光标移动到屏幕坐标 (x, y)，不按键（用于悬停/定位）。"""
        self._platform.move_to(x, y)

    def click(self, x: int, y: int) -> None:
        """左键单击屏幕坐标。"""
        self._platform.click(x, y)

    def double_click(self, x: int, y: int) -> None:
        """左键双击屏幕坐标。"""
        self._platform.double_click(x, y)

    def right_click(self, x: int, y: int) -> None:
        """右键单击屏幕坐标。"""
        self._platform.right_click(x, y)

    def middle_click(self, x: int, y: int) -> None:
        """中键（滚轮按下）单击屏幕坐标。"""
        self._platform.middle_click(x, y)

    def mouse_down(
        self, button: str = "left", x: Optional[int] = None, y: Optional[int] = None
    ) -> None:
        """按下并按住鼠标键（``"left"|"right"|"middle"``）。可先移动到 (x,y)。

        与 :meth:`mouse_up` 配合可实现自定义拖拽、框选、长按等。"""
        self._platform.mouse_down(button=button, x=x, y=y)

    def mouse_up(
        self, button: str = "left", x: Optional[int] = None, y: Optional[int] = None
    ) -> None:
        """松开鼠标键（``"left"|"right"|"middle"``）。可先移动到 (x,y)。"""
        self._platform.mouse_up(button=button, x=x, y=y)

    def drag(self, x1: int, y1: int, x2: int, y2: int) -> None:
        """按住左键从 (x1,y1) 拖到 (x2,y2)。"""
        self._platform.drag(x1, y1, x2, y2)

    def scroll(
        self,
        direction: str,
        amount: int = 3,
        x: Optional[int] = None,
        y: Optional[int] = None,
    ) -> None:
        """滚动滚轮。direction: ``up/down/left/right``；amount 为格数。

        给定 x,y 时先把光标移到该坐标再滚动（滚轮作用于光标所在控件）。"""
        self._platform.scroll(direction, amount, x=x, y=y)

    # ------------------------------------------------------------------ #
    # 基础输入：键盘
    # ------------------------------------------------------------------ #
    def type_text(self, text: str) -> None:
        self._platform.type_text(text)

    def key_press(self, key: str) -> None:
        self._platform.key_press(key)

    # ------------------------------------------------------------------ #
    # 高层语义动作（agent 最常用）
    # ------------------------------------------------------------------ #
    def click_button(
        self,
        window: Window,
        name: str,
        exact: bool = True,
        index: int = 0,
    ) -> Element:
        """在 ``window`` 里按名字找按钮并点击。"""
        from .actions.click import click_button

        return click_button(self._platform, window, name=name, exact=exact, index=index)

    def click_text(self, window: Window, text: str, index: int = 0) -> Element:
        """在 ``window`` 里点击名字包含 ``text`` 的任意元素。"""
        from .actions.click import click_text

        return click_text(self._platform, window, text=text, index=index)

    def type_into(
        self,
        window: Window,
        field: str,
        text: str,
        clear: bool = True,
    ) -> Element:
        """在 ``window`` 里按标签找到输入框并填入文本。"""
        from .actions.type_text import type_into

        return type_into(self._platform, window, field=field, text=text, clear=clear)

    def wait_for(
        self,
        text: Optional[str] = None,
        name: Optional[str] = None,
        window: Optional[Window] = None,
        timeout: float = 10.0,
        poll_interval: float = 0.5,
    ) -> Element:
        """轮询等待匹配元素出现。"""
        from .actions.wait import wait_for

        return wait_for(
            self._platform,
            text=text,
            name=name,
            window=window,
            timeout=timeout,
            poll_interval=poll_interval,
        )

    def wait_until_gone(
        self,
        text: Optional[str] = None,
        name: Optional[str] = None,
        window: Optional[Window] = None,
        timeout: float = 10.0,
        poll_interval: float = 0.5,
    ) -> None:
        """轮询等待匹配元素消失。"""
        from .actions.wait import wait_until_gone

        wait_until_gone(
            self._platform,
            text=text,
            name=name,
            window=window,
            timeout=timeout,
            poll_interval=poll_interval,
        )

    def fill_form(
        self,
        window: Window,
        fields: dict[str, str],
        clear: bool = True,
    ) -> dict[str, object]:
        """批量填表：``{字段标签: 值}``。"""
        from .actions.form import fill_form

        return fill_form(self._platform, window, fields=fields, clear=clear)

    # ------------------------------------------------------------------ #
    # 视觉 / OCR
    # ------------------------------------------------------------------ #
    def find_text(self, text: str, region: Optional[Rect] = None) -> list[Rect]:
        """用 OCR 在屏幕上找文字位置（需要 ``desktop-pilot[ocr]``）。"""
        from .vision.ocr import find_text

        return find_text(self._platform, text=text, region=region)

    def screenshot_b64(self, max_size_kb: int = 500) -> str:
        """截图并返回 base64 JPEG，方便传给多模态 LLM。"""
        from .vision.screenshot import screenshot_b64

        return screenshot_b64(self._platform, max_size_kb=max_size_kb)

    def screenshot_to_file(self, path: str) -> str:
        """截图并存到文件。"""
        from .vision.screenshot import screenshot_to_file

        return screenshot_to_file(self._platform, path)

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #
    def close(self) -> None:
        self._platform.close()

    def __enter__(self) -> "Desktop":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"<Desktop platform={self._platform_name!r}>"
