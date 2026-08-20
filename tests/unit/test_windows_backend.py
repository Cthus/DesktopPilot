"""T05 Windows 后端的纯逻辑单测。

真实鼠标/键盘/窗口枚举在集成测试里验证；这里通过 mock pyautogui / win32 依赖，
只测不依赖真实 GUI 的部分：控件类型映射、组合键解析、异常包装。
"""
from __future__ import annotations

import sys
import types

import pytest

from desktop_pilot.core.types import Rect


# --------------------------------------------------------------------------- #
# 不依赖 Windows 专属依赖的纯函数测试
# --------------------------------------------------------------------------- #
def test_control_type_map_and_unknown():
    # 直接导入模块体里定义的映射（模块本身在无 pywin32 时仍可 import，
    # 只是 WindowsPlatform 构造会抛 PlatformError）。
    from desktop_pilot.platforms import windows as win

    assert win._map_control_type("Button").value == "Button"
    assert win._map_control_type("Edit").value == "Edit"
    assert win._map_control_type("ComboBox").value == "ComboBox"
    assert win._map_control_type("不存在的类型").value == "Unknown"
    assert win._map_control_type(None).value == "Unknown"


def test_safe_rect_from_object_and_tuple():
    from desktop_pilot.platforms.windows import _safe_rect

    class R:
        left, top, right, bottom = 1, 2, 3, 4

    assert _safe_rect(R()) == Rect(1, 2, 3, 4)
    assert _safe_rect((0, 0, 10, 20)) == Rect(0, 0, 10, 20)
    assert _safe_rect("garbage") == Rect(0, 0, 0, 0)


def test_mod_alias_normalizes_ctrl_and_cmd():
    assert "ctrl" in {"ctrl": 1}, "sanity"
    # _MOD_ALIASES 把 control -> ctrl, cmd/windows -> win
    from desktop_pilot.platforms.windows import _MOD_ALIASES

    assert _MOD_ALIASES["control"] == "ctrl"
    assert _MOD_ALIASES["cmd"] == "win"
    assert _MOD_ALIASES["windows"] == "win"


# --------------------------------------------------------------------------- #
# 用 mock 依赖构造 WindowsPlatform，测 key_press 解析
# --------------------------------------------------------------------------- #
@pytest.fixture
def win_platform(monkeypatch):
    """构造一个 WindowsPlatform，其 pyautogui / win32 依赖全部被 mock。"""
    import desktop_pilot.platforms.windows as win_mod

    # mock pyautogui：记录 hotkey / press / scroll 调用
    fake_pyautogui = types.SimpleNamespace(
        FAILSAFE=True,
        PAUSE=0.0,
        click=lambda **k: None,
        write=lambda *a, **k: None,
        press=lambda *a, **k: None,
        hotkey=lambda *a, **k: None,
        scroll=lambda *a, **k: None,
        hscroll=lambda *a, **k: None,
        moveTo=lambda *a, **k: None,
        mouseDown=lambda *a, **k: None,
        mouseUp=lambda *a, **k: None,
        screenshot=lambda *a, **k: None,
    )
    monkeypatch.setitem(sys.modules, "pyautogui", fake_pyautogui)
    monkeypatch.setattr(win_mod, "pyautogui", fake_pyautogui)

    # mock win32 依赖，让 _HAS_WIN32 检查通过
    monkeypatch.setattr(win_mod, "_HAS_WIN32", True)
    sendinput_calls: list[tuple[int, int]] = []

    def fake_send_input(n, lp, cb_size):
        # 记录 (scan code, flags) 从结构里读出来
        import ctypes

        inp = ctypes.cast(lp, ctypes.POINTER(win_mod._INPUT)).contents  # type: ignore[arg-type]
        ki = inp.union.ki
        sendinput_calls.append((ki.wScan, ki.dwFlags))
        return 1  # 成功注入 1 个事件

    fake_user32 = types.SimpleNamespace(
        ShowWindow=lambda *a: 0,
        GetForegroundWindow=lambda: 0,
        GetWindowThreadProcessId=lambda *a: 0,
        AttachThreadInput=lambda *a: 0,
        SetForegroundWindow=lambda *a: 0,
        SetFocus=lambda *a: 0,
        BringWindowToTop=lambda *a: 0,
        SendInput=fake_send_input,
    )
    platform = win_mod.WindowsPlatform.__new__(win_mod.WindowsPlatform)
    platform._apps = {}
    platform._user32 = fake_user32
    return platform, fake_pyautogui, sendinput_calls


def test_key_press_single(win_platform):
    p, pg, _ = win_platform
    calls = []
    pg.press = lambda k: calls.append(("press", k))
    p.key_press("enter")
    p.key_press("TAB")
    assert calls == [("press", "enter"), ("press", "tab")]


def test_key_press_combo(win_platform):
    p, pg, _ = win_platform
    calls = []
    pg.hotkey = lambda *a: calls.append(a)
    p.key_press("ctrl+c")
    p.key_press("alt+f4")
    p.key_press("Ctrl+Shift+Esc")
    assert calls == [
        ("ctrl", "c"),
        ("alt", "f4"),
        ("ctrl", "shift", "esc"),
    ]


def test_scroll_directions(win_platform):
    p, pg, _ = win_platform
    calls = []
    pg.scroll = lambda n: calls.append(("v", n))
    pg.hscroll = lambda n: calls.append(("h", n))

    p.scroll("up", 3)
    p.scroll("down", 5)
    p.scroll("left", 2)
    p.scroll("right", 4)
    assert calls == [("v", 3), ("v", -5), ("h", -2), ("h", 4)]


def test_scroll_invalid_direction(win_platform):
    p, _, _ = win_platform
    with pytest.raises(ValueError):
        p.scroll("sideways")


def test_type_text_and_empty(win_platform):
    p, pg, _ = win_platform
    written = []
    pg.write = lambda text, interval=0.0: written.append(text)
    p.type_text("hello")
    p.type_text("")  # 空串不调用 write
    assert written == ["hello"]


def test_drag_issues_mouse_sequence(win_platform):
    p, pg, _ = win_platform
    seq = []
    pg.moveTo = lambda x, y, **k: seq.append(("move", x, y))
    pg.mouseDown = lambda *a, **k: seq.append(("down",))
    pg.mouseUp = lambda *a, **k: seq.append(("up",))
    p.drag(0, 0, 100, 50)
    assert ("move", 0, 0) in seq
    assert ("down",) in seq
    assert ("move", 100, 50) in seq
    assert ("up",) in seq


def test_click_delegates(win_platform):
    p, pg, _ = win_platform
    calls = []
    pg.click = lambda **k: calls.append(k)
    p.click(10, 20)
    p.double_click(30, 40)
    p.right_click(50, 60)
    assert calls[0]["x"] == 10 and calls[0]["button"] == "left"
    assert calls[1]["clicks"] == 2
    assert calls[2]["button"] == "right"


def test_close_clears_app_cache(win_platform):
    p, _, _ = win_platform
    p._apps["hwnd"] = object()
    p.close()
    assert p._apps == {}


def test_type_text_routes_non_ascii_to_sendinput(win_platform):
    """中文/非 ASCII 字符必须走 SendInput KEYEVENTF_UNICODE（回归测试）。"""
    p, pg, send_calls = win_platform
    written = []
    pg.write = lambda text, interval=0.0: written.append(text)

    p.type_text("ab中文cd")

    # ASCII 连续段 "ab" 和 "cd" 走 pyautogui.write
    assert written == ["ab", "cd"]
    # "中"(U+4E2D) 和 "文"(U+6587) 各发 down + up = 4 个 SendInput 事件
    scans = [sc for sc, _ in send_calls]
    assert 0x4E2D in scans
    assert 0x6587 in scans
    # 每个字符先 down(UNICODE) 再 up(UNICODE|KEYUP)
    assert len(send_calls) == 4
    assert send_calls[0] == (0x4E2D, 0x0004)
    assert send_calls[1] == (0x4E2D, 0x0004 | 0x0002)


def test_type_text_routes_newline_and_tab(win_platform):
    p, pg, _ = win_platform
    keys = []
    pg.press = lambda k: keys.append(k)
    written = []
    pg.write = lambda text, interval=0.0: written.append(text)

    p.type_text("a\nb\tc")
    assert written == ["a", "b", "c"]
    assert keys == ["enter", "tab"]


def test_sendinput_failure_raises_platform_error(win_platform):
    """SendInput 返回 0（事件未注入）时应抛 PlatformError，不能静默丢字。"""
    p, _, send_calls = win_platform

    def failing(n, lp, cb):
        return 0

    p._user32.SendInput = failing
    from desktop_pilot.core.exceptions import PlatformError

    with pytest.raises(PlatformError):
        p.type_text("中")


def test_constructor_raises_without_win32(monkeypatch):
    import desktop_pilot.platforms.windows as win_mod

    monkeypatch.setattr(win_mod, "_HAS_WIN32", False)
    from desktop_pilot.core.exceptions import PlatformError

    with pytest.raises(PlatformError):
        win_mod.WindowsPlatform()
