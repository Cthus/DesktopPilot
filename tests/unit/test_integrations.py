"""T16 LangChain + T17 Function Calling 集成单测。"""
from __future__ import annotations

import json
import sys
import types

import pytest

from desktop_pilot import Desktop, Rect
from desktop_pilot.integrations.function_call import get_tools_schema

from .conftest import (
    FakePlatform,
    attach_roots,
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
# Function Calling schema
# --------------------------------------------------------------------------- #
def test_function_call_schema_is_valid_json():
    schema = get_tools_schema()
    blob = json.dumps(schema)  # 不抛即合法
    assert isinstance(blob, str)
    assert len(schema) >= 5


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

    for required in (
        "desktop_screenshot",
        "desktop_list_windows",
        "desktop_click",
        "desktop_type_text",
        "desktop_key_press",
    ):
        assert required in names


# --------------------------------------------------------------------------- #
# LangChain
# --------------------------------------------------------------------------- #
def _install_fake_langchain(monkeypatch):
    """注入一个最小的假 langchain_core.tools.BaseTool。"""
    pkg = types.ModuleType("langchain_core")
    tools_mod = types.ModuleType("langchain_core.tools")

    class BaseTool:
        name: str = ""
        description: str = ""

    tools_mod.BaseTool = BaseTool
    pkg.tools = tools_mod

    monkeypatch.setitem(sys.modules, "langchain_core", pkg)
    monkeypatch.setitem(sys.modules, "langchain_core.tools", tools_mod)


def test_langchain_requires_optional_dep(monkeypatch):
    # langchain_core 未安装 -> 抛带安装提示的 ImportError。
    monkeypatch.setitem(sys.modules, "langchain_core", None)

    from desktop_pilot.integrations import langchain as lc

    with pytest.raises(ImportError, match="langchain"):
        lc.get_tools(types.SimpleNamespace(_platform=object()))


def test_langchain_tools_construct_and_proxy(monkeypatch):
    _install_fake_langchain(monkeypatch)

    from desktop_pilot.integrations import langchain as lc

    w = make_window("测试窗口")
    attach_roots(w, [make_text("完成", Rect(0, 0, 1, 1))])
    fake = FakePlatform(windows=[w], screenshot_png=_png_bytes())
    bot = Desktop(platform=fake)

    tools = lc.get_tools(bot)
    assert len(tools) >= 5
    names = {t.name for t in tools}
    assert {"desktop_screenshot", "desktop_click_button", "desktop_wait_for"} <= names

    # 截图工具代理到 vision 层，返回 base64 字符串。
    shot = next(t for t in tools if t.name == "desktop_screenshot")
    result = shot._run()
    assert isinstance(result, str) and result

    # list_windows 工具返回 dict 列表。
    lw = next(t for t in tools if t.name == "desktop_list_windows")
    assert lw._run()[0]["name"] == "测试窗口"

    # click 工具记录坐标。
    click = next(t for t in tools if t.name == "desktop_click")
    click._run(30, 40)
    assert fake.clicks == [(30, 40)]

    bot.close()
