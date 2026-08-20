"""高级语义动作层（agent 友好）。

这些函数在底层 :class:`~desktop_pilot.core.platform.Platform` 之上
提供"按名字点按钮""按标签填输入框""等元素出现"等语义能力。
"""
from __future__ import annotations

from .click import click_button, click_text
from .form import fill_form
from .type_text import type_into
from .wait import wait_for, wait_until_gone

__all__ = [
    "click_button",
    "click_text",
    "fill_form",
    "type_into",
    "wait_for",
    "wait_until_gone",
]
