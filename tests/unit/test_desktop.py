"""T06 顶层 Desktop API 单测（注入 FakePlatform，不依赖真实 OS）。"""
from __future__ import annotations

import pytest

from desktop_pilot import (
    Desktop,
    ElementNotFoundError,
    Rect,
    WaitTimeoutError,
    __version__,
)

from .conftest import (
    FakePlatform,
    attach_roots,
    make_button,
    make_edit,
    make_text,
    make_window,
)


def test_version():
    assert __version__ == "0.2.0"


def test_context_manager_calls_close():
    fake = FakePlatform()
    with Desktop(platform=fake) as bot:
        assert bot.platform is fake
    assert fake.closed is True


def test_basic_proxy_methods():
    fake = FakePlatform(screenshot_png=b"PNGDATA")
    with Desktop(platform=fake) as bot:
        assert bot.screenshot() == b"PNGDATA"
        bot.move_to(5, 6)
        bot.click(10, 20)
        bot.double_click(11, 22)
        bot.right_click(30, 40)
        bot.middle_click(50, 60)
        bot.mouse_down("left", 1, 2)
        bot.mouse_up("left", 3, 4)
        bot.type_text("hi")
        bot.key_press("enter")
        bot.drag(0, 0, 100, 100)
        bot.scroll("down", amount=5, x=7, y=8)
    assert fake.clicks == [(10, 20)]
    assert fake.typed == ["hi"]
    assert fake.keys == ["enter"]
    assert ("move_to", (5, 6)) in fake.calls
    assert ("double_click", (11, 22)) in fake.calls
    assert ("right_click", (30, 40)) in fake.calls
    assert ("middle_click", (50, 60)) in fake.calls
    assert ("mouse_down", ("left", 1, 2)) in fake.calls
    assert ("mouse_up", ("left", 3, 4)) in fake.calls
    assert ("drag", (0, 0, 100, 100)) in fake.calls
    assert fake.scrolls == [("down", 5, 7, 8)]


def test_find_window_proxy():
    w = make_window("记事本")
    fake = FakePlatform(windows=[w])
    with Desktop(platform=fake) as bot:
        assert bot.find_window(title="记事本") is w
        assert bot.list_windows() == [w]


def test_click_button_semantic():
    w = make_window()
    btn = make_button("确定", Rect(10, 10, 110, 40))  # center (60,25)
    attach_roots(w, [btn])
    fake = FakePlatform(windows=[w])
    with Desktop(platform=fake) as bot:
        result = bot.click_button(window=w, name="确定")
    assert result is btn
    assert fake.clicks == [(60, 25)]


def test_click_button_not_found():
    w = make_window()
    attach_roots(w, [make_button("确定", Rect(0, 0, 10, 10))])
    fake = FakePlatform(windows=[w])
    with Desktop(platform=fake) as bot, pytest.raises(ElementNotFoundError):
        bot.click_button(window=w, name="取消")


def test_type_into_semantic():
    w = make_window()
    edit = make_edit("用户名输入框", Rect(0, 0, 200, 30))
    attach_roots(w, [edit])
    fake = FakePlatform(windows=[w])
    with Desktop(platform=fake) as bot:
        bot.type_into(window=w, field="用户名", text="admin")
    # 先点击中心，再 ctrl+a / delete 清空，再输入
    assert fake.clicks == [(100, 15)]
    assert "ctrl+a" in fake.keys
    assert "delete" in fake.keys
    assert fake.typed == ["admin"]


def test_fill_form():
    w = make_window()
    user = make_edit("用户名", Rect(0, 0, 200, 30))
    pwd = make_edit("密码", Rect(0, 40, 200, 70))
    attach_roots(w, [user, pwd])
    fake = FakePlatform(windows=[w])
    with Desktop(platform=fake) as bot:
        result = bot.fill_form(w, {"用户名": "admin", "密码": "123"})
    assert set(result.keys()) == {"用户名", "密码"}
    assert fake.typed == ["admin", "123"]


def test_wait_for_finds_element():
    w = make_window()
    label = make_text("加载完成", Rect(0, 0, 100, 20))
    attach_roots(w, [label])
    fake = FakePlatform(windows=[w])
    with Desktop(platform=fake) as bot:
        el = bot.wait_for(text="加载完成", timeout=1, poll_interval=0.05)
    assert el is label


def test_wait_for_timeout():
    w = make_window()
    attach_roots(w, [make_text("别的", Rect(0, 0, 1, 1))])
    fake = FakePlatform(windows=[w])
    with Desktop(platform=fake) as bot, pytest.raises(WaitTimeoutError):
        bot.wait_for(text="不存在", timeout=0.2, poll_interval=0.05)


def test_wait_for_requires_argument():
    with Desktop(platform=FakePlatform()) as bot:
        with pytest.raises(ValueError):
            bot.wait_for(timeout=0.1)
