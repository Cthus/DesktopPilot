"""MCP server 单测：用假 Desktop 直接驱动注册的处理器，不启动子进程。

覆盖：
- create_server 构造成功并注册了 tools/list 与 tools/call；
- tools/list 返回的工具与注册表同源；
- tools/call 能分发、返回 MCP content blocks；
- 未知工具被转成 is_error 结果而不是抛异常。

可选依赖：``mcp``（``pip install 'desktop-pilot[mcp]'``）。
"""
from __future__ import annotations

import json

import pytest

from desktop_pilot import Desktop, Rect

from .conftest import FakePlatform, attach_roots, make_button, make_window

mcp = pytest.importorskip("mcp")


def _server_with(fake: FakePlatform):
    from desktop_pilot.integrations.mcp_server import create_server

    bot = Desktop(platform=fake)
    return create_server(bot), bot


def _call(server, method, params):
    entry = server._request_handlers[method]
    import asyncio

    return asyncio.get_event_loop().run_until_complete(
        entry.handler(None, params)
    )


def test_server_lists_tools_from_registry():
    from desktop_pilot.tools import ToolRegistry
    from mcp.types import PaginatedRequestParams

    fake = FakePlatform(windows=[make_window("记事本", hwnd=1)])
    server, bot = _server_with(fake)

    assert "tools/list" in server._request_handlers
    result = _call(server, "tools/list", PaginatedRequestParams())
    names = [t.name for t in result.tools]
    assert names == ToolRegistry(bot).names()
    assert len(names) >= 20
    # 每个 tool 都带描述和 inputSchema（MCP 2.0 的 python 属性是 snake_case）
    for t in result.tools:
        assert t.description
        assert t.input_schema["type"] == "object"
    bot.close()


def test_server_call_tool_dispatches_and_returns_content():
    from mcp.types import CallToolRequestParams

    w = make_window("设置", hwnd=1)
    attach_roots(w, [make_button("确定", Rect(0, 0, 100, 40))])
    fake = FakePlatform(windows=[w])
    server, bot = _server_with(fake)

    result = _call(
        server,
        "tools/call",
        CallToolRequestParams(
            name="desktop_click_button",
            arguments={"window": "设置", "name": "确定"},
        ),
    )
    assert result.is_error is False
    # 第一段是 text content，是结构化 JSON
    text_block = next(c for c in result.content if c.type == "text")
    payload = json.loads(text_block.text)
    assert payload["ok"] is True
    assert payload["result"]["clicked"]["name"] == "确定"
    # 真的点到了按钮中心 (50, 20)
    assert fake.clicks == [(50, 20)]
    bot.close()


def test_server_call_unknown_tool_is_error_not_exception():
    from mcp.types import CallToolRequestParams

    server, bot = _server_with(FakePlatform())
    result = _call(
        server,
        "tools/call",
        CallToolRequestParams(name="desktop_nope", arguments={}),
    )
    assert result.is_error is True
    text_block = next(c for c in result.content if c.type == "text")
    payload = json.loads(text_block.text)
    assert payload["ok"] is False
    assert payload["error"]["type"] == "UnknownTool"
    bot.close()
