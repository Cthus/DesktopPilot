"""轮询等待元素出现 / 消失。"""
from __future__ import annotations

import time
from typing import Optional

from ..core.element import ControlType, Element, Window
from ..core.exceptions import WaitTimeoutError
from ..core.platform import Platform


def _matches(el: Element, text: Optional[str], name: Optional[str]) -> bool:
    label = el.name or ""
    if text is not None and text in label:
        return True
    if name is not None and label == name:
        return True
    return False


def wait_for(
    platform: Platform,
    text: Optional[str] = None,
    name: Optional[str] = None,
    window: Optional[Window] = None,
    timeout: float = 10.0,
    poll_interval: float = 0.5,
    control_type: Optional[ControlType] = None,
) -> Element:
    """轮询直到匹配元素出现，返回该元素。

    - ``text``：元素名字包含该子串即命中。
    - ``name``：元素名字完全相等即命中。
    - ``window``：给定则只在该窗口内找；``None`` 则遍历所有可见窗口。
    - 超时抛 :class:`WaitTimeoutError`。
    """
    if text is None and name is None:
        raise ValueError("wait_for 至少要提供 text 或 name 之一")

    deadline = time.monotonic() + timeout
    last_count = 0
    while True:
        try:
            windows = [window] if window is not None else platform.list_windows()
            for win in windows:
                try:
                    roots = platform.list_elements(win)
                except Exception:
                    continue
                for root in roots:
                    for el in root.walk():
                        if control_type is not None and el.control_type != control_type:
                            continue
                        if _matches(el, text, name):
                            return el
                last_count = len(windows)
        except Exception:
            # 轮询期间的瞬态错误忽略，继续重试直到超时。
            pass

        if time.monotonic() >= deadline:
            break
        time.sleep(poll_interval)

    raise WaitTimeoutError(
        f"等待 {timeout:.1f}s 后仍未找到 text={text!r} name={name!r}"
        f"（检查了约 {last_count} 个窗口）",
        details={"text": text, "name": name, "timeout": timeout, "windows_scanned": last_count},
    )


def wait_until_gone(
    platform: Platform,
    text: Optional[str] = None,
    name: Optional[str] = None,
    window: Optional[Window] = None,
    timeout: float = 10.0,
    poll_interval: float = 0.5,
) -> None:
    """轮询直到匹配元素消失，超时抛 :class:`WaitTimeoutError`。"""
    if text is None and name is None:
        raise ValueError("wait_until_gone 至少要提供 text 或 name 之一")

    deadline = time.monotonic() + timeout
    while True:
        found = False
        try:
            windows = [window] if window is not None else platform.list_windows()
            for win in windows:
                try:
                    roots = platform.list_elements(win)
                except Exception:
                    continue
                for root in roots:
                    for el in root.walk():
                        if _matches(el, text, name):
                            found = True
                            break
                    if found:
                        break
                if found:
                    break
        except Exception:
            pass

        if not found:
            return

        if time.monotonic() >= deadline:
            break
        time.sleep(poll_interval)

    raise WaitTimeoutError(
        f"等待 {timeout:.1f}s 后元素仍存在: text={text!r} name={name!r}",
        details={"text": text, "name": name, "timeout": timeout},
    )
