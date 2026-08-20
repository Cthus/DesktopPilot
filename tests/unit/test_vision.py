"""T13 OCR + T14 截图工具单测。"""
from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from desktop_pilot.core.types import Rect
from desktop_pilot.vision.ocr import find_text
from desktop_pilot.vision.screenshot import screenshot_b64, screenshot_to_file

from .conftest import FakePlatform


def _make_png(color=(255, 0, 0), size=(40, 30)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_screenshot_to_file(tmp_path):
    png = _make_png()
    fake = FakePlatform(screenshot_png=png)
    out = tmp_path / "shot.png"
    screenshot_to_file(fake, str(out))
    assert out.exists()
    assert out.read_bytes() == png


def test_screenshot_b64_returns_decodable_jpeg():
    png = _make_png(size=(200, 150))
    fake = FakePlatform(screenshot_png=png)
    b64 = screenshot_b64(fake, max_size_kb=500)
    raw = base64.b64decode(b64)
    # JPEG 魔数
    assert raw[:2] == b"\xff\xd8"
    img = Image.open(io.BytesIO(raw))
    assert img.size == (200, 150)


def test_screenshot_b64_respects_region():
    png = _make_png(size=(200, 200))
    fake = FakePlatform(screenshot_png=png)
    b64 = screenshot_b64(fake, max_size_kb=500, region=Rect(0, 0, 50, 50))
    img = Image.open(io.BytesIO(base64.b64decode(b64)))
    assert img.size == (50, 50)


def test_screenshot_b64_compresses_under_limit():
    # 给一张大的纯色（高度可压缩）图，目标体积远低于 q=80 的 JPEG，
    # 验证函数会一路降质量直到达标。
    img = Image.new("RGB", (1200, 900), (123, 200, 50))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    fake = FakePlatform(screenshot_png=buf.getvalue())

    limit_kb = 8  # 纯色大图在最低质量下应能压到 8KB 以内
    b64 = screenshot_b64(fake, max_size_kb=limit_kb)
    assert len(base64.b64decode(b64)) <= limit_kb * 1024


def test_find_text_requires_pytesseract(monkeypatch):
    # 模拟 pytesseract 未安装：import 失败时给友好提示。
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pytesseract":
            raise ImportError("no pytesseract")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    fake = FakePlatform(screenshot_png=_make_png())
    with pytest.raises(ImportError, match="pytesseract"):
        find_text(fake, "hello")


def test_find_text_parses_ocr_results(monkeypatch):
    # mock 掉 pytesseract，喂一组 image_to_data 结果。
    import sys
    import types

    fake_tess = types.ModuleType("pytesseract")

    class _Output:
        DICT = "dict"

    fake_tess.Output = _Output
    fake_tess.image_to_data = lambda *a, **k: {
        "text": ["开始", "提交按钮", "其它"],
        "left": [10, 100, 0],
        "top": [20, 200, 0],
        "width": [40, 80, 1],
        "height": [20, 30, 1],
    }
    monkeypatch.setitem(sys.modules, "pytesseract", fake_tess)

    fake = FakePlatform(screenshot_png=_make_png(size=(500, 500)))
    results = find_text(fake, "提交")
    assert len(results) == 1
    rect = results[0]
    assert rect == Rect(100, 200, 180, 230)


def test_find_text_with_region_offset(monkeypatch):
    import sys
    import types

    fake_tess = types.ModuleType("pytesseract")

    class _Output:
        DICT = "dict"

    fake_tess.Output = _Output
    fake_tess.image_to_data = lambda *a, **k: {
        "text": ["OK"],
        "left": [5],
        "top": [5],
        "width": [10],
        "height": [10],
    }
    monkeypatch.setitem(sys.modules, "pytesseract", fake_tess)

    fake = FakePlatform(screenshot_png=_make_png(size=(500, 500)))
    results = find_text(fake, "OK", region=Rect(100, 200, 300, 400))
    assert results == [Rect(105, 205, 115, 215)]
