"""T09 高级点击 actions 单测。"""
from __future__ import annotations

import pytest

from desktop_pilot.actions.click import click_button, click_text
from desktop_pilot.core.element import ControlType, Element
from desktop_pilot.core.exceptions import ElementNotFoundError
from desktop_pilot.core.types import Rect

from .conftest import (
    FakePlatform,
    attach_roots,
    make_button,
    make_text,
    make_window,
)


def test_click_button_hits_center():
    w = make_window()
    btn = make_button("发送", Rect(100, 200, 200, 240))  # center (150,220)
    attach_roots(w, [btn])
    fake = FakePlatform(windows=[w])

    result = click_button(fake, w, name="发送")
    assert result is btn
    assert fake.clicks == [(150, 220)]


def test_click_button_nested_child():
    w = make_window()
    pane = Element("pane", ControlType.PANE, Rect(0, 0, 300, 300))
    btn = make_button("确定", Rect(0, 0, 60, 30))
    pane.children = [btn]
    btn.parent = pane
    attach_roots(w, [pane])
    fake = FakePlatform(windows=[w])

    click_button(fake, w, name="确定")
    assert fake.clicks == [(30, 15)]


def test_click_button_substring_and_index():
    w = make_window()
    b1 = make_button("发送给A", Rect(0, 0, 10, 10))
    b2 = make_button("发送给B", Rect(100, 100, 140, 140))
    attach_roots(w, [b1, b2])
    fake = FakePlatform(windows=[w])

    click_button(fake, w, name="发送", exact=False, index=1)
    assert fake.clicks == [(120, 120)]


def test_click_button_not_found():
    w = make_window()
    attach_roots(w, [make_button("OK", Rect(0, 0, 10, 10))])
    fake = FakePlatform(windows=[w])

    with pytest.raises(ElementNotFoundError) as ei:
        click_button(fake, w, name="Cancel")
    assert "Cancel" in str(ei.value)
    assert w.name in str(ei.value)


def test_click_button_index_out_of_range():
    w = make_window()
    attach_roots(w, [make_button("OK", Rect(0, 0, 10, 10))])
    fake = FakePlatform(windows=[w])
    with pytest.raises(ElementNotFoundError):
        click_button(fake, w, name="OK", index=5)


def test_click_text_matches_any_type():
    w = make_window()
    label = make_text("欢迎使用", Rect(10, 10, 110, 40))  # center (60,25)
    attach_roots(w, [label])
    fake = FakePlatform(windows=[w])

    result = click_text(fake, w, text="欢迎")
    assert result is label
    assert fake.clicks == [(60, 25)]


def test_click_text_not_found():
    w = make_window()
    attach_roots(w, [make_text("你好", Rect(0, 0, 10, 10))])
    fake = FakePlatform(windows=[w])
    with pytest.raises(ElementNotFoundError):
        click_text(fake, w, text="不存在")
