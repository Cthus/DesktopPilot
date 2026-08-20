"""截图辅助：base64 编码、压缩、存盘。

主要用于把屏幕画面喂给多模态 LLM（Computer Use 风格）。
"""
from __future__ import annotations

import base64
import io
from typing import TYPE_CHECKING

from PIL import Image

if TYPE_CHECKING:
    from ..core.platform import Platform
    from ..core.types import Rect


def _png_bytes_to_image(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data)).convert("RGB")


def screenshot_to_file(platform: "Platform", path: str) -> str:
    """截全屏并存到 ``path``，返回路径。"""
    data = platform.screenshot()
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def screenshot_b64(
    platform: "Platform",
    max_size_kb: int = 500,
    region: "Rect | None" = None,
) -> str:
    """截图并返回 base64 编码的 JPEG（无 data: 前缀）。

    - 自动按 ``80 -> 60 -> 40 -> 25`` 依次降低 JPEG 质量，
      直到结果不超过 ``max_size_kb``。
    - ``region`` 指定只截该矩形区域（屏幕绝对坐标）。
    """
    png = platform.screenshot()
    img = _png_bytes_to_image(png)

    if region is not None:
        img = img.crop((region.left, region.top, region.right, region.bottom))

    target_bytes = max_size_kb * 1024
    buf = io.BytesIO()

    for quality in (80, 60, 40, 25):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        if buf.tell() <= target_bytes:
            break

    return base64.b64encode(buf.getvalue()).decode("ascii")
