"""批量填表。"""
from __future__ import annotations

from ..core.element import Window
from ..core.platform import Platform
from .type_text import type_into


def fill_form(
    platform: Platform,
    window: Window,
    fields: dict[str, str],
    clear: bool = True,
) -> dict[str, object]:
    """对每个 (字段标签, 值) 调用 :func:`type_into`。

    - 任何字段找不到输入框都会抛 :class:`ElementNotFoundError`，
      已填字段**不会回滚**（让调用方自行决定如何处理半成品表单）。
    - 返回 ``{字段名: 填入的 Element}`` 映射，方便调用方核对。
    """
    filled: dict[str, object] = {}
    for field_label, value in fields.items():
        element = type_into(platform, window, field_label, value, clear=clear)
        filled[field_label] = element
    return filled
