"""MCP server 单测：用假 Desktop 直接驱动注册的处理器，不启动子进程。

覆盖：
- create_server 构造成功并注册了 list_tools / call_tool；
- list_tools 返回的工具与注册表同源；
- call_tool 能分发、返回 MCP content blocks；
- 未知工具被转成 isError 结果而不是抛异常。

可选依赖：``mcp``（``pip install 'desktop-pilot[mcp]'``）。测试针对 mcp 1.x
（Hermes pin 的是 mcp==1.26.0）：handler 接收一个 request 对象（``req.params``），
返回包在 ``ServerResult`` 里，字段为 ``isError`` / ``inputSchema``。
"""
from __future__ import annotations

import asyncio
import json

import pytest

from desktop_pilot import Desktop, Rect

from .conftest import FakePlatform, attach_roots, make_button, make_window

mcp = pytest.importorskip("mcp")


def _server_with(fake: FakePlatform):
    from desktop_pilot.integrations.mcp_server import create_server

    bot = Desktop(platform=fake)
    return create_server(bot), bot


_METHOD = {
    "ListToolsRequest": "tools/list",
    "CallToolRequest": "tools/call",
}


def _call(server, request_type, params):
    """直接驱动 mcp server 的 request handler，解开 ServerResult 外壳。"""
    handler = server.request_handlers[request_type]
    req = request_type(method=_METHOD[request_type.__name__], params=params)
    result = asyncio.get_event_loop().run_until_complete(handler(req))
    # 1.x 的 handler 返回 ServerResult(root=...)；解开拿真正的 payload。
    return getattr(result, "root", result)


def _list_tools(server):
    import mcp.types as types

    return _call(server, types.ListToolsRequest, types.PaginatedRequestParams())


def _call_tool(server, name, arguments):
    import mcp.types as types

    params = types.CallToolRequestParams(name=name, arguments=arguments)
    return _call(server, types.CallToolRequest, params)


def test_server_lists_tools_from_registry():
    from desktop_pilot.tools import ToolRegistry

    fake = FakePlatform(windows=[make_window("记事本", hwnd=1)])
    server, bot = _server_with(fake)

    result = _list_tools(server)
    names = [t.name for t in result.tools]
    assert names == ToolRegistry(bot).names()
    assert len(names) >= 20
    # 每个 tool 都带描述和 inputSchema（mcp 1.x 是 camelCase）
    for t in result.tools:
        assert t.description
        assert t.inputSchema["type"] == "object"
    bot.close()


def test_server_call_tool_dispatches_and_returns_content():
    w = make_window("设置", hwnd=1)
    attach_roots(w, [make_button("确定", Rect(0, 0, 100, 40))])
    fake = FakePlatform(windows=[w])
    server, bot = _server_with(fake)

    result = _call_tool(
        server,
        "desktop_click_button",
        {"window": "设置", "name": "确定"},
    )
    assert result.isError is False
    # 第一段是 text content，是结构化 JSON
    text_block = next(c for c in result.content if c.type == "text")
    payload = json.loads(text_block.text)
    assert payload["ok"] is True
    assert payload["result"]["clicked"]["name"] == "确定"
    # 真的点到了按钮中心 (50, 20)
    assert fake.clicks == [(50, 20)]
    bot.close()


def test_server_call_unknown_tool_is_error_not_exception():
    server, bot = _server_with(FakePlatform())
    result = _call_tool(server, "desktop_nope", {})
    assert result.isError is True
    text_block = next(c for c in result.content if c.type == "text")
    payload = json.loads(text_block.text)
    assert payload["ok"] is False
    assert payload["error"]["type"] == "UnknownTool"
    bot.close()
