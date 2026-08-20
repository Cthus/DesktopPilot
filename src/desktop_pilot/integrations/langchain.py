"""LangChain Tool 适配。

把 DesktopPilot 的核心能力包装成 LangChain ``BaseTool`` 列表，
直接喂给 LangChain agent 使用。

    from desktop_pilot import Desktop
    from desktop_pilot.integrations.langchain import get_tools

    with Desktop() as bot:
        tools = get_tools(bot)
        # 把 tools 交给 agent ...
"""
from __future__ import annotations

from typing import Any, Optional

from ..core.element import Element, Window


def get_tools(desktop: Any):
    """返回绑定到给定 :class:`~desktop_pilot.Desktop` 的 LangChain 工具列表。

    需要可选依赖 ``langchain-core``（``pip install desktop-pilot[langchain]``）。
    """
    try:
        from langchain_core.tools import BaseTool  # type: ignore
    except ImportError as exc:  # pragma: no cover - 依赖可选
        raise ImportError(
            "LangChain 集成需要 langchain-core：pip install 'desktop-pilot[langchain]'"
        ) from exc

    def _window_by_substring(title: str) -> Window:
        return desktop.find_window(title_contains=title)

    def _serialize_element(el: Element) -> dict:
        return el.to_dict()

    class ScreenshotTool(BaseTool):
        name: str = "desktop_screenshot"
        description: str = "截取当前屏幕，返回 base64 编码的 JPEG 图像。"

        def _run(self, max_size_kb: int = 500) -> str:  # type: ignore[override]
            from ..vision.screenshot import screenshot_b64

            return screenshot_b64(desktop._platform, max_size_kb=max_size_kb)

    class ListWindowsTool(BaseTool):
        name: str = "desktop_list_windows"
        description: str = "列出当前所有可见顶层窗口（标题、位置、进程）。"

        def _run(self) -> list[dict]:  # type: ignore[override]
            return [w.to_dict() for w in desktop.list_windows()]

    class FindWindowTool(BaseTool):
        name: str = "desktop_find_window"
        description: str = "按标题查找窗口。传 title 精确匹配或 title_contains 子串匹配。"

        def _run(  # type: ignore[override]
            self,
            title: Optional[str] = None,
            title_contains: Optional[str] = None,
        ) -> dict:
            return desktop.find_window(
                title=title, title_contains=title_contains
            ).to_dict()

    class ListElementsTool(BaseTool):
        name: str = "desktop_list_elements"
        description: str = "列出指定窗口的完整 UI 控件树（按窗口标题子串定位窗口）。"

        def _run(self, window: str) -> list[dict]:  # type: ignore[override]
            win = _window_by_substring(window)
            return [_serialize_element(r) for r in desktop.list_elements(window=win)]

    class ClickTool(BaseTool):
        name: str = "desktop_click"
        description: str = "在屏幕绝对坐标 (x, y) 单击鼠标左键。"

        def _run(self, x: int, y: int) -> str:  # type: ignore[override]
            desktop.click(x, y)
            return f"clicked ({x}, {y})"

    class ClickButtonTool(BaseTool):
        name: str = "desktop_click_button"
        description: str = "在指定窗口里按名字找到按钮并点击。window 为窗口标题子串。"

        def _run(  # type: ignore[override]
            self,
            window: str,
            name: str,
            exact: bool = True,
        ) -> str:
            from ..actions.click import click_button

            win = _window_by_substring(window)
            el = click_button(desktop._platform, win, name=name, exact=exact)
            return f"clicked button {el.name!r} at {el.rect.center.to_tuple()}"

    class TypeTextTool(BaseTool):
        name: str = "desktop_type_text"
        description: str = "在当前焦点处逐字输入文本。"

        def _run(self, text: str) -> str:  # type: ignore[override]
            desktop.type_text(text)
            return f"typed {text!r}"

    class TypeIntoTool(BaseTool):
        name: str = "desktop_type_into"
        description: str = "在指定窗口里按标签找到输入框并填入文本（会先清空）。"

        def _run(self, window: str, field: str, text: str) -> str:  # type: ignore[override]
            from ..actions.type_text import type_into

            win = _window_by_substring(window)
            type_into(desktop._platform, win, field=field, text=text)
            return f"filled {field!r} with {text!r}"

    class KeyPressTool(BaseTool):
        name: str = "desktop_key_press"
        description: str = "按键或组合键，例如 'enter'、'tab'、'ctrl+c'、'alt+f4'。"

        def _run(self, key: str) -> str:  # type: ignore[override]
            desktop.key_press(key)
            return f"pressed {key!r}"

    class WaitForTool(BaseTool):
        name: str = "desktop_wait_for"
        description: str = "等待包含指定文本(或精确名字)的元素出现，返回该元素。"

        def _run(  # type: ignore[override]
            self,
            text: Optional[str] = None,
            name: Optional[str] = None,
            timeout: float = 10.0,
        ) -> dict:
            from ..actions.wait import wait_for

            el = wait_for(desktop._platform, text=text, name=name, timeout=timeout)
            return _serialize_element(el)

    return [
        ScreenshotTool(),
        ListWindowsTool(),
        FindWindowTool(),
        ListElementsTool(),
        ClickTool(),
        ClickButtonTool(),
        TypeTextTool(),
        TypeIntoTool(),
        KeyPressTool(),
        WaitForTool(),
    ]


__all__ = ["get_tools"]
