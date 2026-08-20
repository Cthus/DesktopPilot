"""核心抽象层（平台无关）。"""
from __future__ import annotations

from .element import Control, ControlType, Element, Window
from .exceptions import (
    DesktopPilotError,
    ElementNotFoundError,
    PlatformError,
    UnsupportedOperationError,
    WaitTimeoutError,
    WindowNotFoundError,
)
from .platform import Platform
from .types import Point, Rect, Size

__all__ = [
    "Control",
    "ControlType",
    "DesktopPilotError",
    "Element",
    "ElementNotFoundError",
    "Platform",
    "PlatformError",
    "Point",
    "Rect",
    "Size",
    "UnsupportedOperationError",
    "WaitTimeoutError",
    "Window",
    "WindowNotFoundError",
]
