"""OCR 文字定位（pytesseract 兜底）。

UIA 控件树拿不到文字时（游戏 canvas、自绘控件、部分 Electron 应用），
用截图 + Tesseract OCR 找到屏幕上指定文字的位置。

依赖可选：``pip install desktop-pilot[ocr]``（另需系统安装 Tesseract 引擎）。
引擎缺失时这里的报错是可操作的 :class:`~desktop_pilot.core.exceptions.OCRUnavailableError`
（带 details：缺什么、怎么修），让 agent 能自己判断而不是拿到一个裸异常。
"""
from __future__ import annotations

import io
import os
import shutil
from typing import TYPE_CHECKING

from PIL import Image

from ..core.exceptions import OCRUnavailableError
from ..core.types import Rect

if TYPE_CHECKING:
    from ..core.platform import Platform

# Windows / macOS / Linux 常见 Tesseract 安装候选路径（探测用）。
_TESSERACT_CANDIDATES = (
    "C:/Program Files/Tesseract-OCR/tesseract.exe",
    "C:/Program Files (x86)/Tesseract-OCR/tesseract.exe",
    "C:/Users/{user}/AppData/Local/Programs/Tesseract-OCR/tesseract.exe",
    "/usr/bin/tesseract",
    "/opt/homebrew/bin/tesseract",
    "/usr/local/bin/tesseract",
)


def _tesseract_cmd_available() -> bool:
    """探测系统里是否真有 tesseract 引擎（PATH 或常见安装路径）。"""
    if shutil.which("tesseract"):
        return True
    return any(os.path.exists(p.format(user=os.environ.get("USERNAME", ""))) for p in _TESSERACT_CANDIDATES)


def _ensure_ocr_ready():
    """确保 OCR 链路可用；缺依赖/引擎时抛可操作的 OCRUnavailableError。

    返回已导入的 ``pytesseract`` 模块。
    """
    try:
        import pytesseract  # type: ignore
    except ImportError as exc:
        raise OCRUnavailableError(
            "OCR 不可用：缺少 pytesseract 包。"
            "修复：pip install 'desktop-pilot[ocr]'",
            details={
                "pytesseract_installed": False,
                "tesseract_installed": _tesseract_cmd_available(),
                "fix": "pip install 'desktop-pilot[ocr]'",
            },
        ) from exc

    # pytesseract 包在，但要确认引擎在。get_tesseract_version 会去找 tesseract
    # 可执行文件；老版本 pytesseract 无此方法则退回路径探测。
    probe = getattr(pytesseract, "get_tesseract_version", None)
    try:
        if callable(probe):
            probe()
        elif not _tesseract_cmd_available():
            raise OSError("未找到 tesseract 可执行文件")
    except Exception as exc:  # noqa: BLE001 - 引擎探测失败统一归类
        raise OCRUnavailableError(
            "pytesseract 已装，但找不到 OCR 引擎（tesseract.exe）。"
            "修复：安装 Tesseract-OCR（Windows: "
            "https://github.com/UB-Mannheim/tesseract/wiki），"
            "或设置 TESSERACT_CMD 环境变量指向 tesseract 可执行文件。",
            details={
                "pytesseract_installed": True,
                "tesseract_installed": False,
                "searched_paths": list(_TESSERACT_CANDIDATES),
                "fix": "安装 Tesseract-OCR 或设置 TESSERACT_CMD",
                "env_tesseract_cmd": os.environ.get("TESSERACT_CMD"),
            },
        ) from exc
    return pytesseract


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

    OCR 链路不可用（缺 pytesseract / 缺 tesseract 引擎）时抛
    :class:`~desktop_pilot.core.exceptions.OCRUnavailableError`，details 带修复指引。
    """
    pytesseract = _ensure_ocr_ready()

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
