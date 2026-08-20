"""DesktopPilot 的 MCP (Model Context Protocol) server。

把工具注册表 :class:`~desktop_pilot.tools.ToolRegistry` 直接暴露为 MCP 工具，
通过 **stdio** 与 MCP 宿主（Claude Desktop / hermes / 任意 MCP client）通信。
工具定义与执行逻辑全部来自注册表，这一层只做协议翻译，不重复声明任何工具。

用法（作为模块运行）::

    python -m desktop_pilot.integrations.mcp_server

在 MCP 客户端配置里加一个 stdio server：

.. code-block:: json

    {
      "mcpServers": {
        "desktop-pilot": {
          "command": "python",
          "args": ["-m", "desktop_pilot.integrations.mcp_server"]
        }
      }
    }

需要可选依赖：``pip install 'desktop-pilot[mcp]'``（安装 ``mcp``）。
"""
from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from ..tools import ToolRegistry


def create_server(desktop: Any = None) -> Any:
    """构造并返回一个已注册好工具处理器的 MCP ``Server`` 实例。

    Args:
        desktop: 可选的 :class:`~desktop_pilot.Desktop`。默认懒构造一个。
    """
    try:
        from mcp.server.lowlevel import Server  # type: ignore
        from mcp.types import (  # type: ignore
            CallToolResult,
            ImageContent,
            ListToolsResult,
            TextContent,
            Tool,
        )
    except ImportError as exc:  # pragma: no cover - 仅在缺依赖时触发
        raise ImportError(
            "MCP 集成需要 mcp 包：pip install 'desktop-pilot[mcp]'"
        ) from exc

    if desktop is None:
        from .. import Desktop

        desktop = Desktop()

    registry = ToolRegistry(desktop)

    async def on_list_tools(_ctx: Any, _params: Any) -> Any:
        return ListToolsResult(
            tools=[
                Tool(
                    name=t["name"],
                    description=t["description"],
                    inputSchema=t["inputSchema"],
                )
                for t in registry.mcp_tools()
            ]
        )

    async def on_call_tool(_ctx: Any, params: Any) -> Any:
        result = registry.call(params.name, params.arguments or {})
        payload = result.to_dict(include_image=False)
        blocks: list[Any] = [
            TextContent(
                type="text",
                text=json.dumps(payload, ensure_ascii=False, indent=2),
            )
        ]
        if result.image is not None:
            import base64

            raw, mime = result.image
            blocks.append(
                ImageContent(
                    type="image",
                    data=base64.b64encode(raw).decode("ascii"),
                    mimeType=mime,
                )
            )
        return CallToolResult(content=blocks, is_error=not result.ok)

    server: Any = Server(
        "desktop-pilot",
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )
    return server


async def _run_stdio() -> None:
    """用 stdio transport 运行 server（不自动关闭 Desktop，进程退出即清理）。"""
    from mcp.server.stdio import stdio_server  # type: ignore

    server = create_server()

    # Desktop 实例保存在注册表的闭包里；进程退出时 OS 会回收资源。
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    """控制台入口：``python -m desktop_pilot.integrations.mcp_server``。"""
    try:
        asyncio.run(_run_stdio())
    except KeyboardInterrupt:  # pragma: no cover
        sys.exit(0)


if __name__ == "__main__":
    main()
