"""desktop_wait_for_text / desktop_wait_until_text_gone 单测（OCR 轮询等待）。"""
from __future__ import annotations

import time

from desktop_pilot import Desktop, Rect
from desktop_pilot.tools import ToolRegistry

from .conftest import FakePlatform


def _set_find_text_sequence(monkeypatch, sequence):
    """让 find_text 按 sequence 顺序返回；耗尽后一直返回最后一项。

    sequence: list of list[Rect] —— 每次调用给一份结果。
    """
    from desktop_pilot.vision import ocr as ocr_mod

    calls = {"n": 0}

    def fake_find_text(platform, text, region=None, lang="chi_sim+eng"):
        i = min(calls["n"], len(sequence) - 1)
        calls["n"] += 1
        return list(sequence[i])

    monkeypatch.setattr(ocr_mod, "find_text", fake_find_text)


def test_wait_for_text_returns_when_appears(monkeypatch):
    # 前两次空（没出现），第三次出现
    _set_find_text_sequence(monkeypatch, [[], [], [Rect(0, 0, 20, 20)]])
    bot = Desktop(platform=FakePlatform())
    reg = ToolRegistry(bot)
    r = reg.call("desktop_wait_for_text", {"text": "已发送", "timeout": 5, "poll_interval": 0.01})
    assert r.ok, r.error
    assert r.value["found"]["text"] == "已发送"
    assert r.value["found"]["rect"] == [0, 0, 20, 20]


def test_wait_for_text_times_out(monkeypatch):
    _set_find_text_sequence(monkeypatch, [[], []])
    bot = Desktop(platform=FakePlatform())
    reg = ToolRegistry(bot)
    t0 = time.monotonic()
    r = reg.call("desktop_wait_for_text", {"text": "永远没有", "timeout": 0.05, "poll_interval": 0.01})
    assert r.ok is False
    assert r.error["type"] == "WaitTimeoutError"
    assert r.error["details"]["text"] == "永远没有"
    assert time.monotonic() - t0 < 2  # 及时返回，不长挂


def test_wait_until_text_gone_returns_when_disappears(monkeypatch):
    # 先出现（等待中），随后消失
    _set_find_text_sequence(monkeypatch, [[Rect(0, 0, 10, 10)], [], []])
    bot = Desktop(platform=FakePlatform())
    reg = ToolRegistry(bot)
    r = reg.call("desktop_wait_until_text_gone", {"text": "加载中", "timeout": 5, "poll_interval": 0.01})
    assert r.ok, r.error
    assert r.value["gone"]["text"] == "加载中"


def test_wait_until_text_gone_times_out(monkeypatch):
    _set_find_text_sequence(monkeypatch, [[Rect(0, 0, 10, 10)]])
    bot = Desktop(platform=FakePlatform())
    reg = ToolRegistry(bot)
    r = reg.call("desktop_wait_until_text_gone", {"text": "一直在", "timeout": 0.05, "poll_interval": 0.01})
    assert r.ok is False
    assert r.error["type"] == "WaitTimeoutError"
    assert r.error["details"]["last_matches"] >= 1

    # 两个工具都在注册表里
    names = reg.names()
    assert "desktop_wait_for_text" in names
    assert "desktop_wait_until_text_gone" in names