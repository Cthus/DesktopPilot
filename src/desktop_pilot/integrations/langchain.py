"""LangChain Tool 适配（基于工具注册表自动派生）。

所有工具定义都在 :mod:`desktop_pilot.tools` 里，本模块把每个
:class:`~desktop_pilot.tools.ToolSpec` 动态包装成一个 LangChain ``BaseTool``，
不再手写第二份名字/描述/参数，避免漂移。

    from desktop_pilot import Desktop
    from desktop_pilot.integrations.langchain import get_tools

    with Desktop() as bot:
        tools = get_tools(bot)
        # 把 tools 交给 LangChain agent ...
"""
from __future__ import annotations

import json
from typing import Any

from ..tools import ToolRegistry


def get_tools(desktop: Any) -> list[Any]:
    """返回绑定到给定 :class:`~desktop_pilot.Desktop` 的 LangChain 工具列表。

    需要可选依赖 ``langchain-core``（``pip install 'desktop-pilot[langchain]'``）。
    """
    try:
        from langchain_core.tools import StructuredTool  # type: ignore
    except ImportError as exc:  # pragma: no cover - 依赖可选
        raise ImportError(
            "LangChain 集成需要 langchain-core：pip install 'desktop-pilot[langchain]'"
        ) from exc

    registry = ToolRegistry(desktop)

    def make_runner(spec_name: str):
        def _run(**kwargs: Any) -> str:
            result = registry.call(spec_name, kwargs)
            # LangChain 工具返回字符串：序列化成紧凑 JSON，图像只给摘要。
            return json.dumps(result.to_dict(include_image=False), ensure_ascii=False)

        return _run

    tools: list[Any] = []
    for spec in registry.specs():
        tool = StructuredTool(
            name=spec.name,
            description=spec.description,
            args_schema=_build_args_schema(spec),
            func=make_runner(spec.name),
        )
        tools.append(tool)
    return tools


def _build_args_schema(spec: Any) -> Any:
    """从 ToolSpec 的 JSON Schema 动态生成 pydantic 参数模型。

    langchain 的 StructuredTool 用 pydantic 模型做参数校验/文档；这里用
    pydantic v2 的 ``create_model`` 直接从 JSON Schema 的 properties 生成，
    保证与注册表的 schema 同源。
    """
    try:
        from pydantic import Field, create_model  # type: ignore
    except ImportError as exc:  # pragma: no cover - langchain-core 依赖 pydantic
        raise ImportError("LangChain 集成需要 pydantic：pip install pydantic") from exc

    parameters = spec.parameters or {}
    properties = parameters.get("properties", {})
    required = set(parameters.get("required", []))

    fields: dict[str, Any] = {}
    for pname, pschema in properties.items():
        py_type = _json_type_to_python(pschema)
        default = pschema.get("default", ... if pname in required else None)
        desc = pschema.get("description", "")
        if "enum" in pschema:
            # pydantic 用 Literal 表达枚举
            from typing import Literal

            py_type = Literal[tuple(pschema["enum"])]  # type: ignore
        fields[pname] = (py_type, Field(default=default, description=desc))

    return create_model(f"{spec.name}_args", **fields)


def _json_type_to_python(schema: dict[str, Any]) -> Any:
    t = schema.get("type")
    if t == "integer":
        return int
    if t == "number":
        return float
    if t == "boolean":
        return bool
    if t == "array":
        from typing import List

        items = schema.get("items", {})
        return List[_json_type_to_python(items)]  # type: ignore
    if t == "object":
        return dict
    return str


__all__ = ["get_tools"]
