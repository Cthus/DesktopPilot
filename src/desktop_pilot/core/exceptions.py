"""DesktopPilot 异常体系。

所有异常继承自 DesktopPilotError，上层可统一 catch。
注意：超时异常命名为 ``WaitTimeoutError`` 以避开内置的 ``TimeoutError``。
"""
from __future__ import annotations

from typing import Any, Optional


class DesktopPilotError(Exception):
    """所有 DesktopPilot 异常的基类。"""

    def __init__(self, message: str = "", details: Optional[dict[str, Any]] = None) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} ({self.details})"
        return self.message

    def with_details(self, **kw: Any) -> "DesktopPilotError":
        """链式补充排查上下文：``raise E(...).with_details(window=..., name=...)``。

        ``None`` 值跳过，避免污染 details。
        """
        for key, value in kw.items():
            if value is not None:
                self.details[key] = value
        return self

    @property
    def traceback_text(self) -> str:
        """把异常被 raise 时的调用栈格式化成多行文本（跨边界取用）。

        只要异常在 raise 处被捕获，``__traceback__`` 就被 Python 填好，
        在分发边界读此属性即可拿到完整堆栈，便于落日志 / 返回给调用方。
        """
        import traceback

        return "".join(traceback.format_exception(type(self), self, self.__traceback__))


class ElementNotFoundError(DesktopPilotError):
    """在控件树里找不到目标控件时抛出。"""


class WindowNotFoundError(DesktopPilotError):
    """找不到匹配的窗口时抛出。"""


class WaitTimeoutError(DesktopPilotError):
    """``wait_for`` 轮询超时时抛出。

    故意不命名为 ``TimeoutError``，避免与 Python 内置异常冲突。
    """


class PlatformError(DesktopPilotError):
    """平台后端调用失败（COM 错误、权限问题等）时抛出。"""


class OCRUnavailableError(DesktopPilotError):
    """OCR 引擎不可用时抛出（缺 pytesseract，或系统未装 Tesseract 二进制）。

    设计意图：这类失败是 agent 可感知、可修复的（装依赖 / 设 TESSERACT_CMD），
    属于**预期错误**——details 会带上具体缺什么、怎么修，而不是裸 InternalError。
    """


class UnsupportedOperationError(DesktopPilotError):
    """当前平台不支持某操作（如 macOS/Linux stub）时抛出。"""
