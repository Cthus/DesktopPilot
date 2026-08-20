"""按名字定位输入框并输入文本。"""
from __future__ import annotations

from ..core.element import ControlType, Element, Window
from ..core.exceptions import ElementNotFoundError
from ..core.platform import Platform
from .click import _activate


def _find_edit(platform: Platform, window: Window, field: str) -> Element:
    """找 name 含 ``field`` 的 Edit 控件；field 为空时返回第一个 Edit。"""
    target = field.casefold()
    fallback: Element | None = None
    for root in platform.list_elements(window):
        for el in root.walk():
            if el.control_type != ControlType.EDIT:
                continue
            if fallback is None:
                fallback = el
            if target and target in (el.name or "").casefold():
                return el
    # 没按名字命中但 field 给了：报错。
    if target:
        raise ElementNotFoundError(
            f"在窗口 {window.name!r} 里找不到标签含 {field!r} 的输入框",
            details={"window": window.name, "field": field},
        )
    if fallback is None:
        raise ElementNotFoundError(
            f"在窗口 {window.name!r} 里没有任何输入框(Edit)",
            details={"window": window.name},
        )
    return fallback


def type_into(
    platform: Platform,
    window: Window,
    field: str,
    text: str,
    clear: bool = True,
) -> Element:
    """在 ``window`` 里找到标签含 ``field`` 的输入框，点击聚焦后输入 ``text``。

    - ``clear=True``（默认）先 Ctrl+A 再 Delete 清空已有内容。
    - 找不到输入框抛 :class:`ElementNotFoundError`。
    返回被填入的输入框元素。
    """
    edit = _find_edit(platform, window, field)
    _activate(platform, window)

    center = edit.rect.center
    platform.click(center.x, center.y)

    if clear:
        platform.key_press("ctrl+a")
        platform.key_press("delete")

    platform.type_text(text)
    return edit
