"""Agent 工具注册表——DesktopPilot 对 AI agent 的统一接口层。

这是所有 agent 集成（OpenAI/Anthropic function-calling、LangChain、MCP）
的**唯一真相源**。每个工具只在此处定义一次（名字、描述、参数 schema、
执行逻辑），各集成层从 :class:`~desktop_pilot.tools.registry.ToolRegistry`
自动派生，避免多份手写定义漂移。

典型用法::

    from desktop_pilot import Desktop
    from desktop_pilot.tools import ToolRegistry

    with Desktop() as bot:
        reg = ToolRegistry(bot)
        schemas = reg.openai_schema()        # 给 function-calling
        result = reg.call("desktop_click", {"x": 100, "y": 200})  # 分发
        blocks = result.to_content()         # 给 MCP（含图片）
"""
from __future__ import annotations

from .registry import ToolRegistry
from .spec import ToolResult, ToolSpec

__all__ = ["ToolRegistry", "ToolSpec", "ToolResult"]
