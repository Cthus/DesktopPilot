"""OpenAI / Anthropic 兼容的 function calling JSON schema。

``get_tools_schema()`` 返回的列表可直接塞给 OpenAI ``chat.completions``
的 ``tools`` 参数，或 Anthropic Messages 的 ``tools`` 字段。
"""
from __future__ import annotations

from typing import Any


def get_tools_schema() -> list[dict[str, Any]]:
    """返回一组桌面自动化工具的 JSON schema。"""
    return [
        {
            "type": "function",
            "function": {
                "name": "desktop_screenshot",
                "description": "截取当前屏幕，返回 base64 编码的 JPEG 图像。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "max_size_kb": {
                            "type": "integer",
                            "description": "返回图像的最大体积（KB），超出会自动压缩。",
                            "default": 500,
                        }
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "desktop_list_windows",
                "description": "列出当前所有可见的顶层窗口，返回标题、句柄、位置等。",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "desktop_find_window",
                "description": "按标题精确/子串匹配找到一个窗口。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "窗口标题精确匹配"},
                        "title_contains": {
                            "type": "string",
                            "description": "窗口标题包含的子串",
                        },
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "desktop_list_elements",
                "description": "列出指定窗口的所有 UI 控件（按钮/输入框/文本等结构化控件树）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "window": {
                            "type": "string",
                            "description": "目标窗口标题（子串匹配）",
                        }
                    },
                    "required": ["window"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "desktop_click",
                "description": "在屏幕绝对坐标处单击鼠标左键。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer", "description": "横坐标像素"},
                        "y": {"type": "integer", "description": "纵坐标像素"},
                    },
                    "required": ["x", "y"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "desktop_click_button",
                "description": "在指定窗口内按名字找到按钮并点击（无需坐标）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "window": {"type": "string", "description": "窗口标题子串"},
                        "name": {"type": "string", "description": "按钮名字"},
                        "exact": {
                            "type": "boolean",
                            "description": "是否精确匹配名字，默认 true",
                            "default": True,
                        },
                    },
                    "required": ["window", "name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "desktop_type_text",
                "description": "在当前焦点处逐字输入文本。",
                "parameters": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "desktop_type_into",
                "description": "在指定窗口里按标签找到输入框并填入文本。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "window": {"type": "string", "description": "窗口标题子串"},
                        "field": {
                            "type": "string",
                            "description": "输入框标签/名字包含的子串",
                        },
                        "text": {"type": "string", "description": "要填入的文本"},
                    },
                    "required": ["window", "field", "text"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "desktop_key_press",
                "description": "按键或组合键，如 'enter'、'tab'、'ctrl+c'、'alt+f4'。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {
                            "type": "string",
                            "description": "键名或用 '+' 连接的组合键",
                        }
                    },
                    "required": ["key"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "desktop_wait_for",
                "description": "轮询等待某个文本/命名元素出现，返回元素信息。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "等待元素名字包含的文本"},
                        "name": {"type": "string", "description": "等待元素的精确名字"},
                        "timeout": {
                            "type": "number",
                            "description": "最长等待秒数",
                            "default": 10,
                        },
                    },
                    "required": [],
                },
            },
        },
    ]


__all__ = ["get_tools_schema"]
