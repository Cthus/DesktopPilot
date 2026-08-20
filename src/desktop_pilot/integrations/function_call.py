"""OpenAI / Anthropic 兼容的 function-calling JSON schema。

历史上本模块手写了一份工具 schema；现在所有工具的唯一真相源在
:mod:`desktop_pilot.tools`（:class:`~desktop_pilot.tools.ToolRegistry`），
本模块只是从注册表派生出 OpenAI/Anthropic 格式的薄封装。

需要执行工具时（拿到模型的 tool_call 后），请直接用注册表的分发器::

    from desktop_pilot import Desktop
    from desktop_pilot.tools import ToolRegistry

    bot = Desktop()
    registry = ToolRegistry(bot)
    result = registry.call(tool_call.name, tool_call.arguments)
"""
from __future__ import annotations

from typing import Any, Optional

from ..tools import ToolRegistry

_default_registry: Optional[ToolRegistry] = None


def _get_registry(desktop: Any = None) -> ToolRegistry:
    """拿到一个注册表实例。

    - 传入 desktop 时用它（执行工具必需）；
    - 仅取 schema（不执行）时 desktop 可省略，内部懒构造一个 Desktop——
      schema 与平台无关，构造后端不会产生真实输入副作用。
    """
    global _default_registry
    if desktop is not None:
        return ToolRegistry(desktop)
    if _default_registry is None:
        from .. import Desktop

        _default_registry = ToolRegistry(Desktop())
    return _default_registry


def get_tools_schema(desktop: Any = None) -> list[dict[str, Any]]:
    """返回 OpenAI/Anthropic function-calling 工具声明列表。

    Args:
        desktop: 可选的 :class:`~desktop_pilot.Desktop` 实例；仅生成 schema
            时不需要传。若你还要 :func:`call_tool`，请传同一个 desktop 以便
            共享实例与缓存。
    """
    return _get_registry(desktop).openai_schema()


def call_tool(name: str, arguments: dict[str, Any] | None = None, desktop: Any = None):
    """按名字分发执行一个工具，返回结构化结果。

    这是给原生 function-calling agent 用的执行器：模型返回 tool_call 后，
    直接把 ``name`` / ``arguments`` 丢进来即可，无需自己写 if/else 分发。
    """
    return _get_registry(desktop).call(name, arguments or {})


__all__ = ["get_tools_schema", "call_tool"]
