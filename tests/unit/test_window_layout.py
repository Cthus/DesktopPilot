"""窗口化理解：desktop_list_windows 的 z-order / active 信息。

验证 agent 拿到的是"当前屏幕堆叠了哪些窗口、谁在前、谁是焦点"，
而不只是一堆平铺的 id/title。
"""
from __future__ import annotations

import types

from desktop_pilot import Desktop, Rect
from desktop_pilot.tools import ToolRegistry

from .conftest import FakePlatform, make_window


def test_list_windows_reports_z_order_and_active():
    # 三个窗口：w1 最先枚举=z 序最底，w3 最后=z 序最顶
    w1 = make_window("底窗口", hwnd=1)
    w2 = make_window("中窗口", hwnd=2)
    w3 = make_window("顶窗口", hwnd=3)
    fake = FakePlatform(windows=[w1, w2, w3])
    bot = Desktop(platform=fake)

    # 模拟前台窗口 = 顶窗口 w3(hwnd=3)
    fake._user32 = types.SimpleNamespace(GetForegroundWindow=lambda: 3)

    reg = ToolRegistry(bot)
    r = reg.call("desktop_list_windows", {})
    assert r.ok, r.error
    wins = r.value

    # 顺序应保持：底 -> 顶（w1,z=2最底; w3,z=0最前/顶）
    titles = [w["title"] for w in wins]
    assert titles == ["底窗口", "中窗口", "顶窗口"]
    # z: 最前(z=0)是顶窗口
    assert wins[2]["z"] == 0 and wins[2]["active"] is True
    assert wins[0]["z"] == 2 and wins[0]["active"] is False
    assert wins[1]["z"] == 1
    # 每个窗口都有 center（默认 rect 0,0,800,600 → center 400,300）
    assert wins[0]["center"] == [400, 300]
    bot.close()


def test_list_windows_no_foreground_all_false():
    # 取不到前台时(无 _user32)，active 全为 False，不崩
    w = make_window("唯一", hwnd=5)
    fake = FakePlatform(windows=[w])
    reg = ToolRegistry(Desktop(platform=fake))
    r = reg.call("desktop_list_windows", {})
    assert r.ok, r.error
    assert r.value[0]["active"] is False
    assert r.value[0]["z"] == 0


def test_list_windows_single_window_z_zero():
    w = make_window("单个", hwnd=9)
    fake = FakePlatform(windows=[w])
    fake._user32 = types.SimpleNamespace(GetForegroundWindow=lambda: 9)
    reg = ToolRegistry(Desktop(platform=fake))
    r = reg.call("desktop_list_windows", {})
    assert r.value[0]["z"] == 0
    assert r.value[0]["active"] is True


def test_minimized_window_flagged():
    # Windows 最小化窗口 rect 是屏幕外坐标(-32000 等) → 标记 minimized=True
    from desktop_pilot.core.element import ControlType, Window

    w_min = Window(name="最小化", control_type=ControlType.WINDOW,
                   rect=Rect(-32000, -32000, -31900, -31900), hwnd=6)
    w_norm = Window(name="正常", control_type=ControlType.WINDOW,
                    rect=Rect(0, 0, 800, 600), hwnd=7)
    fake = FakePlatform(windows=[w_min, w_norm])
    fake._user32 = types.SimpleNamespace(GetForegroundWindow=lambda: 7)
    reg = ToolRegistry(Desktop(platform=fake))
    r = reg.call("desktop_list_windows", {})
    by_title = {w["title"]: w for w in r.value}
    assert by_title["最小化"]["minimized"] is True
    assert by_title["正常"]["minimized"] is False