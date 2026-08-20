"""function-calling / LangChain / 工具注册表集成层单测。

新架构下所有工具定义都在 :mod:`desktop_pilot.tools`，function_call 与
langchain 都是从注册表派生的薄封装；这里验证三件事：

1. function-calling schema 合法且包含核心工具；
2. ``call_tool`` 分发器能真正执行并返回结构化结果；
3. LangChain 集成（可选依赖）能构造工具并代理调用。
"""
from __future__ import annotations

import json

import pytest

from desktop_pilot import Desktop, Rect
from desktop_pilot.integrations.function_call import call_tool, get_tools_schema
from desktop_pilot.tools import ToolRegistry

from .conftest import (
    FakePlatform,
    attach_roots,
    make_button,
    make_edit,
    make_text,
    make_window,
)


def _png_bytes(color=(10, 20, 30), size=(32, 24)) -> bytes:
    import io as _io

    from PIL import Image as _Image

    buf = _io.BytesIO()
    _Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# 工具注册表（唯一真相源）
# --------------------------------------------------------------------------- #
def test_registry_exposes_full_tool_set():
    bot = Desktop(platform=FakePlatform())
    reg = ToolRegistry(bot)
    names = reg.names()
    # 核心：感知
    assert {
        "desktop_screenshot",
        "desktop_list_windows",
        "desktop_find_window",
        "desktop_list_elements",
    } <= set(names)
    # 核心：鼠标全套
    assert {
        "desktop_move_mouse",
        "desktop_click",
        "desktop_double_click",
        "desktop_right_click",
        "desktop_middle_click",
        "desktop_mouse_down",
        "desktop_mouse_up",
        "desktop_scroll",
        "desktop_drag",
    } <= set(names)
    # 核心：键盘 + 语义
    assert {
        "desktop_type_text",
        "desktop_key_press",
        "desktop_click_button",
        "desktop_click_text",
        "desktop_type_into",
        "desktop_fill_form",
        "desktop_wait_for",
        "desktop_wait_until_gone",
    } <= set(names)
    bot.close()


def test_registry_every_schema_is_valid_and_unique():
    bot = Desktop(platform=FakePlatform())
    reg = ToolRegistry(bot)
    seen: set[str] = set()
    for spec in reg.specs():
        assert spec.name not in seen, f"重复工具名 {spec.name}"
        seen.add(spec.name)
        assert spec.description and len(spec.description) > 10
        params = spec.parameters
        assert params["type"] == "object"
        assert "properties" in params
        # 声明为 required 的字段必须存在于 properties
        for req in params.get("required", []):
            assert req in params["properties"], f"{spec.name}: required {req} 未声明"
    bot.close()


def test_registry_openai_and_mcp_schema_agree():
    """OpenAI schema 与 MCP 工具列表必须同源——同一个 spec 派生。"""
    bot = Desktop(platform=FakePlatform())
    reg = ToolRegistry(bot)
    openai_names = {t["function"]["name"] for t in reg.openai_schema()}
    mcp_names = {t["name"] for t in reg.mcp_tools()}
    assert openai_names == mcp_names
    bot.close()


def test_registry_dispatches_mouse_actions():
    fake = FakePlatform()
    bot = Desktop(platform=fake)
    reg = ToolRegistry(bot)

    assert reg.call("desktop_click", {"x": 10, "y": 20}).ok
    assert ("click", (10, 20)) in fake.calls
    assert reg.call("desktop_right_click", {"x": 1, "y": 2}).ok
    assert ("right_click", (1, 2)) in fake.calls
    assert reg.call("desktop_middle_click", {"x": 3, "y": 4}).ok
    assert ("middle_click", (3, 4)) in fake.calls
    assert reg.call("desktop_move_mouse", {"x": 5, "y": 6}).ok
    assert ("move_to", (5, 6)) in fake.calls
    r = reg.call("desktop_mouse_down", {"button": "middle"})
    assert r.ok and ("mouse_down", ("middle", None, None)) in fake.calls
    r = reg.call("desktop_mouse_up", {"button": "right", "x": 7, "y": 8})
    assert r.ok and ("mouse_up", ("right", 7, 8)) in fake.calls
    r = reg.call("desktop_scroll", {"direction": "down", "amount": 5, "x": 1, "y": 2})
    assert r.ok and ("scroll", ("down", 5, 1, 2)) in fake.calls
    bot.close()


def test_registry_unknown_tool_is_structured_error():
    reg = ToolRegistry(Desktop(platform=FakePlatform()))
    r = reg.call("desktop_nope", {})
    assert not r.ok
    assert r.error is not None and r.error["type"] == "UnknownTool"


def test_registry_screenshot_returns_image():
    fake = FakePlatform(screenshot_png=_png_bytes())
    reg = ToolRegistry(Desktop(platform=fake))
    r = reg.call("desktop_screenshot", {})
    assert r.ok
    assert r.image is not None
    mime, raw = r.image[1], r.image[0]
    assert mime == "image/jpeg"
    assert isinstance(raw, bytes) and len(raw) > 0


def test_registry_window_resolution_by_id_and_title():
    w1 = make_window("记事本", hwnd=111)
    w2 = make_window("计算器", hwnd=222)
    fake = FakePlatform(windows=[w1, w2])
    reg = ToolRegistry(Desktop(platform=fake))

    r = reg.call("desktop_find_window", {"title_contains": "记事"})
    assert r.ok and r.value["id"] == "111" and r.value["pid"] == 42

    # list_elements 用 id 寻址（hwnd 字符串）
    attach_roots(w1, [make_text("完成", Rect(0, 0, 10, 10))])
    r = reg.call("desktop_list_elements", {"window": "111"})
    assert r.ok and any(e["name"] == "完成" for e in r.value)


def test_registry_window_id_not_found_is_structured_error():
    reg = ToolRegistry(Desktop(platform=FakePlatform(windows=[make_window("记事本", hwnd=111)])))
    r = reg.call("desktop_list_elements", {"window": "999"})
    assert not r.ok
    assert r.error is not None and "999" in r.error["message"]


def test_registry_click_button_routes_to_action():
    w = make_window("设置")
    btn = make_button("确定", Rect(100, 100, 200, 140))
    attach_roots(w, [btn])
    fake = FakePlatform(windows=[w])
    bot = Desktop(platform=fake)
    reg = ToolRegistry(bot)

    r = reg.call(
        "desktop_click_button", {"window": "设置", "name": "确定", "exact": True}
    )
    assert r.ok
    # 点击落在按钮中心 (150, 120)
    assert fake.clicks == [(150, 120)]
    bot.close()


def test_registry_type_into_routes_to_action():
    w = make_window("登录")
    edit = make_edit("用户名", Rect(0, 0, 200, 30))
    attach_roots(w, [edit])
    fake = FakePlatform(windows=[w])
    bot = Desktop(platform=fake)
    reg = ToolRegistry(bot)

    r = reg.call(
        "desktop_type_into",
        {"window": "登录", "field": "用户名", "text": "alice", "clear": True},
    )
    assert r.ok
    # 点击聚焦 + 输入文本
    assert fake.typed == ["alice"]
    assert "ctrl+a" in fake.keys and "delete" in fake.keys
    bot.close()


# --------------------------------------------------------------------------- #
# Function-calling 薄封装
# --------------------------------------------------------------------------- #
def test_function_call_schema_is_valid_json():
    schema = get_tools_schema()
    blob = json.dumps(schema)  # 不抛即合法
    assert isinstance(blob, str)
    assert len(schema) == len(ToolRegistry(Desktop(platform=FakePlatform())).names())


def test_function_call_schema_structure():
    schema = get_tools_schema()
    names = set()
    for entry in schema:
        assert entry["type"] == "function"
        fn = entry["function"]
        assert fn["name"] and fn["description"]
        assert fn["parameters"]["type"] == "object"
        assert "properties" in fn["parameters"]
        names.add(fn["name"])
    assert {"desktop_screenshot", "desktop_click", "desktop_type_text"} <= names


def test_call_tool_dispatches_on_given_desktop():
    fake = FakePlatform()
    bot = Desktop(platform=fake)
    r = call_tool("desktop_right_click", {"x": 9, "y": 8}, desktop=bot)
    assert r.ok and ("right_click", (9, 8)) in fake.calls
    bot.close()


# --------------------------------------------------------------------------- #
# LangChain 薄封装（用真实 langchain_core，Python313 已装）
# --------------------------------------------------------------------------- #
def test_langchain_tools_construct_and_proxy():
    pytest.importorskip("langchain_core")
    from desktop_pilot.integrations import langchain as lc

    w = make_window("测试窗口")
    attach_roots(w, [make_text("完成", Rect(0, 0, 1, 1))])
    fake = FakePlatform(windows=[w], screenshot_png=_png_bytes())
    bot = Desktop(platform=fake)

    tools = lc.get_tools(bot)
    assert len(tools) == len(ToolRegistry(bot).names())
    names = {t.name for t in tools}
    assert {
        "desktop_screenshot",
        "desktop_click_button",
        "desktop_wait_for",
        "desktop_middle_click",
        "desktop_scroll",
    } <= names

    # 工具返回 JSON 字符串，解析后是结构化结果。
    click = next(t for t in tools if t.name == "desktop_click")
    out = click.invoke({"x": 30, "y": 40})
    payload = json.loads(out)
    assert payload["ok"] is True
    assert fake.clicks == [(30, 40)]

    lw = next(t for t in tools if t.name == "desktop_list_windows")
    out = lw.invoke({})
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["result"][0]["title"] == "测试窗口"
    bot.close()
