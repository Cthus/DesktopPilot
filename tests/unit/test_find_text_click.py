"""desktop_find_text_click 单测：OCR 定位文字 → 点击中心（自绘界面首选操作）。"""
from __future__ import annotations

from desktop_pilot import Desktop, Rect
from desktop_pilot.tools import ToolRegistry

from .conftest import FakePlatform


def _mock_find_text(monkeypatch, rects):
    from desktop_pilot.vision import ocr as ocr_mod

    monkeypatch.setattr(
        ocr_mod,
        "find_text",
        lambda platform, text, region=None, lang="chi_sim+eng": list(rects),
    )


def _registry_with(monkeypatch, rects):
    _mock_find_text(monkeypatch, rects)
    fake = FakePlatform()
    bot = Desktop(platform=fake)
    return ToolRegistry(bot), fake


def test_click_lands_on_text_center(monkeypatch):
    # find_text 返回 [(10,20)->(40,50)]，中心应为 (25, 35)
    reg, fake = _registry_with(monkeypatch, [Rect(10, 20, 40, 50)])
    r = reg.call("desktop_find_text_click", {"text": "发送"})
    assert r.ok, r.error
    assert fake.clicks == [(25, 35)]
    assert r.value["clicked"]["center"] == [25, 35]
    assert r.value["clicked"]["total_matches"] == 1


def test_click_respects_index(monkeypatch):
    reg, fake = _registry_with(monkeypatch, [Rect(0, 0, 10, 10), Rect(100, 100, 110, 130)])
    r = reg.call("desktop_find_text_click", {"text": "发送", "index": 1})
    assert r.ok, r.error
    # 第二个匹配中心 = (105, 115)
    assert fake.clicks == [(105, 115)]


def test_no_match_is_expected_error(monkeypatch):
    reg, fake = _registry_with(monkeypatch, [])
    r = reg.call("desktop_find_text_click", {"text": "不存在的字"})
    assert r.ok is False
    assert r.error["type"] == "ElementNotFoundError"
    assert "不存在的字" in r.error["message"]
    assert "traceback" not in r.error  # 预期错误：不刷堆栈
    assert fake.clicks == []


def test_index_out_of_range_is_expected_error(monkeypatch):
    reg, fake = _registry_with(monkeypatch, [Rect(0, 0, 10, 10)])
    r = reg.call("desktop_find_text_click", {"text": "发送", "index": 5})
    assert r.ok is False
    assert r.error["type"] == "ElementNotFoundError"
    assert r.error["details"]["count"] == 1


def test_activate_window_when_given(monkeypatch):
    from .conftest import make_window

    _mock_find_text(monkeypatch, [Rect(200, 300, 220, 330)])
    w = make_window("微信", hwnd=7)
    fake = FakePlatform(windows=[w])
    bot = Desktop(platform=fake)
    reg = ToolRegistry(bot)

    r = reg.call("desktop_find_text_click", {"text": "搜索", "window": "微信"})
    assert r.ok, r.error
    # 点击落在匹配中心 (210, 315)
    assert fake.clicks == [(210, 315)]