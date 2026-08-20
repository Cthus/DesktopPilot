"""OCR 文字定位（pytesseract 兜底）。

UIA 控件树拿不到文字时（游戏 canvas、自绘控件、部分 Electron 应用），
用截图 + Tesseract OCR 找到屏幕上指定文字的位置。

依赖可选：``pip install desktop-pilot[ocr]``（另需系统安装 Tesseract 引擎）。
"""
from __future__ import annotations

import io
from typing import TYPE_CHECKING

from PIL import Image

from ..core.types import Rect

if TYPE_CHECKING:
    from ..core.platform import Platform


def find_text(
    platform: "Platform",
    text: str,
    region: Rect | None = None,
    lang: str = "chi_sim+eng",
    case_sensitive: bool = False,
) -> list[Rect]:
    """截屏 + OCR，返回所有匹配 ``text`` 的文字块的矩形列表（屏幕绝对坐标）。

    - ``region`` 只识别该矩形区域（屏幕绝对坐标），可显著提速。
    - ``lang`` 传给 tesseract，默认中英混合。
    - 大小写不敏感匹配（除非 ``case_sensitive=True``）。
    """
    try:
        import pytesseract  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "OCR 功能需要 pytesseract：pip install 'desktop-pilot[ocr]'"
            "（并在系统安装 Tesseract 引擎）"
        ) from exc

    png = platform.screenshot()
    img = Image.open(io.BytesIO(png))

    # 裁剪区域（相对于屏幕原点）。记录原点以便把 OCR 坐标映射回屏幕坐标。
    offset_x, offset_y = 0, 0
    if region is not None:
        img = img.crop((region.left, region.top, region.right, region.bottom))
        offset_x, offset_y = region.left, region.top

    data = pytesseract.image_to_data(
        img, lang=lang, output_type=pytesseract.Output.DICT
    )

    needle = text if case_sensitive else text.casefold()
    results: list[Rect] = []
    n = len(data.get("text", []))
    for i in range(n):
        word = (data["text"][i] or "").strip()
        if not word:
            continue
        hay = word if case_sensitive else word.casefold()
        if needle not in hay:
            continue
        try:
            x = int(data["left"][i]) + offset_x
            y = int(data["top"][i]) + offset_y
            w = int(data["width"][i])
            h = int(data["height"][i])
        except (KeyError, ValueError, TypeError):
            continue
        results.append(Rect(x, y, x + w, y + h))
    return results
