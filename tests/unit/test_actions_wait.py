"""T11 wait_for / wait_until_gone 单测。"""
from __future__ import annotations

import pytest

from desktop_pilot.actions.wait import wait_for, wait_until_gone
from desktop_pilot.core.element import ControlType
from desktop_pilot.core.exceptions import WaitTimeoutError
from desktop_pilot.core.types import Rect

from .conftest import FakePlatform, attach_roots, make_text, make_window


def test_wait_for_returns_immediately(fake_platform):
    w = make_window()
    attach_roots(w, [make_text("加载完成", Rect(0, 0, 100, 20))])
    fake_platform._windows = [w]

    el = wait_for(fake_platform, text="加载完成", timeout=1, poll_interval=0.05)
    assert el.name == "加载完成"


def test_wait_for_polls_until_appears():
    # 第一/二次 list_elements 抛异常（元素尚未出现），第三次命中。
    w = make_window()
    label = make_text("已连接", Rect(0, 0, 50, 20))

    calls = {"n": 0}

    class FlakyPlatform(FakePlatform):
        def list_elements(self, window):
            calls["n"] += 1
            if calls["n"] < 3:
                return [make_text("连接中...", Rect(0, 0, 1, 1))]
            attach_roots(w, [label])
            return super().list_elements(window)

    fake = FlakyPlatform(windows=[w])
    el = wait_for(fake, text="已连接", timeout=2, poll_interval=0.02)
    assert el is label
    assert calls["n"] >= 3


def test_wait_for_timeout():
    w = make_window()
    attach_roots(w, [make_text("其它文字", Rect(0, 0, 1, 1))])
    fake = FakePlatform(windows=[w])

    with pytest.raises(WaitTimeoutError) as ei:
        wait_for(fake, text="不存在", timeout=0.2, poll_interval=0.05)
    assert "不存在" in str(ei.value)


def test_wait_for_name_exact():
    w = make_window()
    attach_roots(w, [make_text("确定", Rect(0, 0, 10, 10))])
    fake = FakePlatform(windows=[w])

    # text 子串能命中 "确定按钮"，name 精确必须等于 "确定"
    el = wait_for(fake, name="确定", timeout=0.2, poll_interval=0.05)
    assert el.name == "确定"


def test_wait_for_requires_argument():
    with pytest.raises(ValueError):
        wait_for(FakePlatform(), timeout=0.1)


def test_wait_for_scoped_to_window():
    w1 = make_window("窗口1")
    attach_roots(w1, [make_text("目标", Rect(0, 0, 10, 10))])
    w2 = make_window("窗口2")
    attach_roots(w2, [make_text("目标", Rect(0, 0, 10, 10))])
    fake = FakePlatform(windows=[w1, w2])

    el = wait_for(fake, text="目标", window=w2, timeout=0.2)
    assert el.parent is w2


def test_wait_until_gone_returns_when_absent():
    w = make_window()
    attach_roots(w, [make_text("临时弹窗", Rect(0, 0, 1, 1))])

    calls = {"n": 0}

    class VanishingPlatform(FakePlatform):
        def list_elements(self, window):
            calls["n"] += 1
            if calls["n"] < 2:
                return super().list_elements(window)
            attach_roots(w, [])
            return super().list_elements(window)

    fake = VanishingPlatform(windows=[w])
    # 不应抛异常
    wait_until_gone(fake, text="临时弹窗", timeout=1, poll_interval=0.02)


def test_wait_until_gone_timeout():
    w = make_window()
    attach_roots(w, [make_text("一直都在", Rect(0, 0, 1, 1))])
    fake = FakePlatform(windows=[w])

    with pytest.raises(WaitTimeoutError):
        wait_until_gone(fake, text="一直都在", timeout=0.2, poll_interval=0.05)
