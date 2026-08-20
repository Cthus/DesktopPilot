"""平台抽象基类。

所有平台后端（Windows / macOS / Linux）必须实现这里声明的方法。
:class:`~desktop_pilot.Desktop` 通过该抽象代理调用，下游可据此 mock。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from .element import Element, Window


class Platform(ABC):
    """平台后端抽象。方法签名是稳定契约，下游照着实现。"""

    @abstractmethod
    def screenshot(self) -> bytes:
        """截取全屏，返回 PNG 字节。"""

    @abstractmethod
    def list_windows(self) -> list[Window]:
        """枚举所有可见的顶层窗口。"""

    @abstractmethod
    def find_window(
        self,
        title: str | None = None,
        title_contains: str | None = None,
        pid: int | None = None,
    ) -> Window:
        """按标题精确/子串或进程 id 查找窗口，找不到抛 WindowNotFoundError。"""

    @abstractmethod
    def list_elements(self, window: Window) -> list[Element]:
        """获取窗口的完整控件树（返回顶层元素，后代通过 children 访问）。"""

    @abstractmethod
    def click(self, x: int, y: int) -> None:
        """在屏幕坐标左键单击。"""

    @abstractmethod
    def double_click(self, x: int, y: int) -> None:
        """在屏幕坐标左键双击。"""

    @abstractmethod
    def right_click(self, x: int, y: int) -> None:
        """在屏幕坐标右键单击。"""

    @abstractmethod
    def type_text(self, text: str) -> None:
        """逐字输入文本（焦点需已在目标控件上）。"""

    @abstractmethod
    def key_press(self, key: str) -> None:
        """按键或组合键，如 ``"enter"`` / ``"tab"`` / ``"ctrl+c"``。"""

    @abstractmethod
    def scroll(self, direction: str, amount: int = 3) -> None:
        """滚动滚轮。direction: up/down/left/right。amount 为滚动格数。"""

    @abstractmethod
    def drag(self, x1: int, y1: int, x2: int, y2: int) -> None:
        """从 (x1,y1) 按住左键拖到 (x2,y2)。"""

    @abstractmethod
    def close(self) -> None:
        """释放后端持有的资源。"""
