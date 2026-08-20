"""工具规格 (ToolSpec) 与统一返回包络 (ToolResult)。

设计目标：

- **一处定义，到处派生**：:class:`ToolSpec` 同时携带给 LLM 看的 JSON schema
  和真正执行的 handler，schema 与执行逻辑永不会漂移。
- **结构化错误**：handler 抛出的任何异常都在分发边界被捕获，转成
  :class:`ToolResult`(ok=False)，agent loop 收到的是可读取的错误而不是崩溃。
- **多模态返回**：截图等工具返回的图像，会同时以 base64 data 形式携带，
  ``to_content()`` 直接给出 MCP / Anthropic 风格的 content block 列表。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ..core.exceptions import DesktopPilotError

# Handler 接收已校验的参数字典，返回任意可 JSON 序列化的值；
# 若返回 (value, image_bytes, image_mime) 三元组则视为带图像结果。
ToolHandler = Callable[[dict[str, Any]], Any]


@dataclass
class ToolSpec:
    """一个 agent 工具的完整定义。

    Attributes:
        name: 工具名，全局唯一（约定以 ``desktop_`` 开头）。
        description: 给 LLM 的说明：做什么、何时用、注意事项。
        parameters: JSON Schema (draft 2020-12 的子集) 描述入参。
        handler: ``lambda args: ...``，args 为已传入的参数字典。
        destructive: 是否为有副作用/不可逆的操作（用于日志与确认）。
    """

    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler
    destructive: bool = False

    # ------------------------------------------------------------------ #
    # 派生各种外部格式
    # ------------------------------------------------------------------ #
    def openai_schema(self) -> dict[str, Any]:
        """OpenAI / Anthropic function-calling 格式的工具声明。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def input_schema(self) -> dict[str, Any]:
        """MCP ``inputSchema`` 字段（即裸 JSON Schema，不带 function 外壳）。"""
        return self.parameters


@dataclass
class ToolResult:
    """工具执行的统一返回包络。

    所有 handler 的返回值都会被包成这个结构。出错时 ``ok=False`` 且
    ``error`` 填充错误类型与消息；成功时 ``value`` 承载结果。若产生图像，
    ``image`` 携带 (bytes, mime)。
    """

    ok: bool = True
    value: Any = None
    error: dict[str, Any] | None = None
    image: tuple[bytes, str] | None = None  # (raw_bytes, mime_type)
    tool_name: str = ""

    # ------------------------------------------------------------------ #
    # 构造器
    # ------------------------------------------------------------------ #
    @classmethod
    def success(
        cls,
        value: Any = None,
        *,
        image: tuple[bytes, str] | None = None,
        tool_name: str = "",
    ) -> "ToolResult":
        return cls(ok=True, value=value, image=image, tool_name=tool_name)

    @classmethod
    def failure(
        cls,
        message: str,
        error_type: str = "DesktopPilotError",
        details: Any | None = None,
        *,
        tool_name: str = "",
    ) -> "ToolResult":
        err: dict[str, Any] = {"type": error_type, "message": message}
        if details is not None:
            err["details"] = details
        return cls(ok=False, error=err, tool_name=tool_name)

    # ------------------------------------------------------------------ #
    # 序列化
    # ------------------------------------------------------------------ #
    def to_dict(self, *, include_image: bool = False) -> dict[str, Any]:
        """转成可 JSON 序列化的字典。

        默认不内联图像字节（体积大）；需要时置 ``include_image=True``，
        图像会以 base64 放入 ``image.data``。
        """
        out: dict[str, Any] = {"ok": self.ok}
        if self.ok:
            out["result"] = self.value
        if self.error is not None:
            out["error"] = self.error
        if self.image is not None:
            raw, mime = self.image
            if include_image:
                import base64

                out["image"] = {
                    "mime_type": mime,
                    "data": base64.b64encode(raw).decode("ascii"),
                }
            else:
                out["image"] = {"mime_type": mime, "bytes": len(raw)}
        if self.tool_name:
            out["tool"] = self.tool_name
        return out

    def to_content(self) -> list[dict[str, Any]]:
        """转成 MCP / Anthropic 风格的 content block 列表。

        - 文本结果 → ``{"type": "text", "text": <json>}``
        - 图像结果 → ``{"type": "image", "source": {type: base64, ...}}``
        """
        import json

        blocks: list[dict[str, Any]] = []
        payload = self.to_dict(include_image=False)
        blocks.append({"type": "text", "text": json.dumps(payload, ensure_ascii=False)})
        if self.image is not None:
            import base64

            raw, mime = self.image
            blocks.append(
                {
                    "type": "image",
                    "data": base64.b64encode(raw).decode("ascii"),
                    "mimeType": mime,
                }
            )
        return blocks


def classify_error(exc: BaseException) -> tuple[str, str]:
    """把异常映射成稳定的 (error_type, message)。"""
    if isinstance(exc, DesktopPilotError):
        return type(exc).__name__, str(exc) or type(exc).__name__
    if isinstance(exc, (ValueError, TypeError, KeyError)):
        return type(exc).__name__, str(exc) or type(exc).__name__
    # 未知异常统一归类，避免把内部堆栈泄露给 LLM。
    return "InternalError", f"{type(exc).__name__}: {exc}"
