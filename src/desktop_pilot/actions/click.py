"""按语义点击：按名字点按钮 / 点含某文本的元素。"""
from __future__ import annotations

from typing import Optional

from ..core.element import ControlType, Element, Window
from ..core.exceptions import ElementNotFoundError
from ..core.platform import Platform


def _activate(platform: Platform, window: Window) -> None:
    """点击前激活窗口（Windows 后端才有 hwnd）。"""
    hwnd = getattr(window, "hwnd", None)
    activator = getattr(platform, "_activate_window", None)
    if hwnd and callable(activator):
        activator(hwnd)


def _iter_elements(platform: Platform, window: Window):
    """遍历窗口控件树里的所有元素。"""
    roots = platform.list_elements(window)
    for root in roots:
        yield from root.walk()


def _find_buttons(
    platform: Platform,
    window: Window,
    name: str,
    exact: bool,
) -> list[Element]:
    matches: list[Element] = []
    target = name.casefold()
    for el in _iter_elements(platform, window):
        if el.control_type not in (ControlType.BUTTON, ControlType.MENUITEM,
                                   ControlType.LINK, ControlType.RADIOBUTTON):
            continue
        label = (el.name or "").casefold()
        if exact:
            if label == target:
                matches.append(el)
        else:
            if target in label:
                matches.append(el)
    return matches


def click_button(
    platform: Platform,
    window: Window,
    name: str,
    exact: bool = True,
    index: int = 0,
) -> Element:
    """在 ``window`` 里找到名字匹配的按钮并点击其中心。

    - ``exact=True`` 名字完全相等（大小写不敏感），否则子串包含。
    - ``index`` 选择第几个匹配（默认第一个）。
    - 找不到抛 :class:`ElementNotFoundError`。
    返回被点击的元素。
    """
    matches = _find_buttons(platform, window, name, exact)
    if not matches:
        raise ElementNotFoundError(
            f"在窗口 {window.name!r} 里找不到按钮 name={name!r} (exact={exact})",
            details={"window": window.name, "name": name, "exact": exact},
        )
    if index < 0 or index >= len(matches):
        raise ElementNotFoundError(
            f"在窗口 {window.name!r} 找到 {len(matches)} 个按钮，但 index={index} 越界",
            details={"window": window.name, "name": name, "count": len(matches), "index": index},
        )

    target = matches[index]
    _activate(platform, window)
    center = target.rect.center
    platform.click(center.x, center.y)
    return target


def click_text(
    platform: Platform,
    window: Window,
    text: str,
    index: int = 0,
) -> Element:
    """点击任意名字包含 ``text`` 的可见元素（不限控件类型）。"""
    target_text = text.casefold()
    matches = [
        el
        for el in _iter_elements(platform, window)
        if el.visible and target_text in (el.name or "").casefold()
    ]
    if not matches:
        raise ElementNotFoundError(
            f"在窗口 {window.name!r} 里找不到包含文本 {text!r} 的元素",
            details={"window": window.name, "text": text},
        )
    if index < 0 or index >= len(matches):
        raise ElementNotFoundError(
            f"找到 {len(matches)} 个含 {text!r} 的元素，但 index={index} 越界",
            details={"window": window.name, "text": text, "count": len(matches)},
        )

    target = matches[index]
    _activate(platform, window)
    center = target.rect.center
    platform.click(center.x, center.y)
    return target
