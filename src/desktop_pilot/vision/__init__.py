"""视觉 / OCR 兜底。

当 UIA 控件树拿不到文字（游戏 canvas、自绘界面、Electron 部分区域）时，
用截图 + OCR 定位屏幕文字。
"""
from __future__ import annotations

from .ocr import find_text
from .screenshot import screenshot_b64, screenshot_to_file

__all__ = ["find_text", "screenshot_b64", "screenshot_to_file"]
