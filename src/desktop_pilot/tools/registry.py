"""工具注册表：所有 agent 工具的唯一定义与统一分发。

每个工具以 :class:`~desktop_pilot.tools.spec.ToolSpec` 形式在
:meth:`ToolRegistry._build` 中注册一次，schema 与执行逻辑绑定在一起，
OpenAI function-calling / LangChain / MCP 都从这里派生。

窗口寻址约定：凡是需要指定窗口的工具，统一用 ``window`` 参数，它**既可以是
``desktop_list_windows`` 返回的窗口 id（hwnd 的十进制字符串，最稳），也可以是
标题子串**。注册表内部的 :meth:`_resolve_window` 负责把两种形式解析成 Window。
"""
from __future__ import annotations

import traceback
from typing import Any, Callable

from ..core.element import Element, Window
from ..core.exceptions import DesktopPilotError, WindowNotFoundError
from ..core.logging import debug_enabled, logger
from .spec import ToolResult, ToolSpec, classify_error


def _element_brief(el: Element) -> dict[str, Any]:
    """元素的精简序列化：给 LLM 看够用，又不会把控件树整段塞回去。"""
    return {
        "name": el.name,
        "control_type": el.control_type.value,
        "rect": el.rect.to_tuple(),
        "center": el.rect.center.to_tuple(),
        "enabled": el.enabled,
        "visible": el.visible,
        "value": el.value,
    }


def _window_brief(win: Window) -> dict[str, Any]:
    return {
        "id": str(win.hwnd) if win.hwnd is not None else None,
        "title": win.name,
        "rect": win.rect.to_tuple(),
        "pid": win.pid,
    }


# --------------------------------------------------------------------------- #
# 复用的 JSON Schema 片段
# --------------------------------------------------------------------------- #
def _window_param(desc: str = "目标窗口：传窗口 id（desktop_list_windows 返回的 id）或标题子串。") -> dict[str, Any]:
    return {"type": "string", "description": desc}


def _opt(name_schema: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in name_schema.items()}


_MOUSE_BTN = {
    "type": "string",
    "enum": ["left", "right", "middle"],
    "description": "鼠标键：left=左键，right=右键，middle=中键（滚轮按下）。",
}
_COORDS = {
    "x": {"type": "integer", "description": "横坐标像素（屏幕绝对坐标）。"},
    "y": {"type": "integer", "description": "纵坐标像素（屏幕绝对坐标）。"},
}
_SCROLL_DIR = {
    "type": "string",
    "enum": ["up", "down", "left", "right"],
    "description": "滚动方向：up/down 垂直，left/right 水平。",
}


class ToolRegistry:
    """绑定到一个 :class:`~desktop_pilot.Desktop` 实例的工具集合。"""

    def __init__(self, desktop: Any) -> None:
        self._bot = desktop
        self._tools: dict[str, ToolSpec] = {}
        self._build()

    # ------------------------------------------------------------------ #
    # 公共 API
    # ------------------------------------------------------------------ #
    def names(self) -> list[str]:
        return list(self._tools.keys())

    def get(self, name: str) -> ToolSpec:
        if name not in self._tools:
            raise KeyError(f"未知工具: {name!r}")
        return self._tools[name]

    def specs(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def openai_schema(self) -> list[dict[str, Any]]:
        """OpenAI / Anthropic function-calling 工具声明列表。"""
        return [t.openai_schema() for t in self._tools.values()]

    def mcp_tools(self) -> list[dict[str, Any]]:
        """MCP ``tools/list`` 负载：{name, description, inputSchema}。"""
        return [
            {"name": t.name, "description": t.description, "inputSchema": t.input_schema()}
            for t in self._tools.values()
        ]

    # ------------------------------------------------------------------ #
    # 分发
    # ------------------------------------------------------------------ #
    def call(self, name: str, arguments: dict[str, Any] | None = None) -> ToolResult:
        """按名字分发执行，捕获所有异常并返回结构化 :class:`ToolResult`。

        失败时自带排查信息：

        - ``error.context.arguments`` —— 当时传入的参数（复现用）；
        - ``error.traceback`` —— 完整调用栈。**预期错误**（DesktopPilotError，
          如"找不到按钮"）默认不带，靠 ``details`` 里的业务上下文；**意外异常**
          才带，因为那才是要修的 bug；``DESKTOP_PILOT_DEBUG=1`` 时两者都带。
        - 同时写入 ``desktop_pilot`` logger（stderr，Hermes 会落 mcp-stderr.log）。
        """
        arguments = arguments or {}
        try:
            spec = self.get(name)
        except KeyError as exc:
            return ToolResult.failure(
                str(exc), error_type="UnknownTool", tool_name=name
            )
        try:
            value, image = self._invoke(spec.handler, arguments)
            return ToolResult.success(value, image=image, tool_name=name)
        except DesktopPilotError as exc:
            return self._failure_from(name, arguments, exc)
        except Exception as exc:  # noqa: BLE001 - 分发边界要兜住一切
            return self._failure_from(name, arguments, exc)

    @staticmethod
    def _failure_from(
        name: str, arguments: dict[str, Any], exc: BaseException
    ) -> ToolResult:
        """把分发边界的异常统一转成带排查信息的 ToolResult。"""
        etype, msg = classify_error(exc)
        details = getattr(exc, "details", None) or None
        tb = getattr(exc, "traceback_text", None) or "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )
        unexpected = not isinstance(exc, DesktopPilotError)

        # 日志：意外异常永远带全栈（定位 bug）；预期错误只打一行（agent loop 正常分支）。
        if unexpected:
            logger.error("[%s] %s: %s\n%s", name, etype, msg, tb)
        elif debug_enabled():
            logger.warning("[%s] %s: %s\n%s", name, etype, msg, tb)
        else:
            logger.warning("[%s] %s: %s", name, etype, msg)

        return ToolResult.failure(
            msg,
            error_type=etype,
            details=details,
            tool_name=name,
            # 意外异常直接在错误里带 traceback，方便在 Hermes 端直接看到是哪一行。
            traceback=tb if (unexpected or debug_enabled()) else None,
            context={"arguments": arguments},
        )

    @staticmethod
    def _invoke(handler: Callable[[dict[str, Any]], Any], args: dict[str, Any]):
        """执行 handler，把 (value, image_bytes, mime) 三元组拆开。"""
        result = handler(args)
        if isinstance(result, tuple) and len(result) == 3 and isinstance(result[1], (bytes, bytearray)):
            value, image_bytes, mime = result
            return value, (bytes(image_bytes), mime)
        return result, None

    # ------------------------------------------------------------------ #
    # 窗口寻址
    # ------------------------------------------------------------------ #
    def _resolve_window(self, ref: Any) -> Window:
        """把窗口 id（hwnd 字符串）或标题子串解析成 Window。

        - 纯数字优先按 hwnd 在已枚举窗口里精确匹配；
        - 否则按标题子串找。
        解析失败抛 WindowNotFoundError（在 call 里被转成结构化错误）。
        """
        if ref is None:
            raise WindowNotFoundError("window 参数不能为空")
        ref = str(ref).strip()
        if ref.isdigit():
            target = int(ref)
            for win in self._bot.list_windows():
                if win.hwnd == target:
                    return win
            raise WindowNotFoundError(
                f"找不到窗口 id={ref}（可能已关闭）", details={"hwnd": target}
            )
        return self._bot.find_window(title_contains=ref)

    # ------------------------------------------------------------------ #
    # 工具注册
    # ------------------------------------------------------------------ #
    def _add(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"工具名重复: {spec.name!r}")
        self._tools[spec.name] = spec

    def _build(self) -> None:
        bot = self._bot

        # ---- 感知 ----------------------------------------------------- #
        self._add(ToolSpec(
            name="desktop_screenshot",
            description=(
                "截取当前整个屏幕，返回 JPEG 图像（同时给出 base64）。"
                "在做任何点击前先截图看清界面；也用于确认操作结果。"
                "返回里的 image 可直接展示给多模态模型。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "max_size_kb": {
                        "type": "integer",
                        "description": "返回图像的最大体积（KB），超出会自动降质量压缩。",
                        "default": 500,
                    }
                },
                "required": [],
            },
            handler=lambda a: self._screenshot(a),
        ))

        self._add(ToolSpec(
            name="desktop_list_windows",
            description=(
                "列出当前所有可见顶层窗口。返回每个窗口的 id（后续操作窗口用这个 id 最稳）、"
                "标题 title、位置 rect、进程 pid。操作前先用它确认目标窗口的 id/标题。"
            ),
            parameters={"type": "object", "properties": {}, "required": []},
            handler=lambda a: [_window_brief(w) for w in bot.list_windows()],
        ))

        self._add(ToolSpec(
            name="desktop_find_window",
            description="按标题查找单个窗口。传 title_contains 做子串匹配（最常用），或 title 精确匹配。",
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "窗口标题精确匹配。"},
                    "title_contains": {"type": "string", "description": "窗口标题包含的子串。"},
                },
                "required": [],
            },
            handler=lambda a: _window_brief(
                bot.find_window(title=a.get("title"), title_contains=a.get("title_contains"))
            ),
        ))

        self._add(ToolSpec(
            name="desktop_list_elements",
            description=(
                "列出指定窗口的完整 UI 控件树（按钮/输入框/文本等结构化信息，含每个控件的"
                "中心坐标 center）。这是'看见'窗口结构的主要手段：先列控件拿到名字和坐标，"
                "再用 desktop_click_button 或 desktop_click 操作。window 传窗口 id 或标题子串。"
            ),
            parameters={
                "type": "object",
                "properties": {"window": _window_param()},
                "required": ["window"],
            },
            handler=lambda a: self._list_elements(a),
        ))

        # ---- 鼠标：移动与点击 ---------------------------------------- #
        self._add(ToolSpec(
            name="desktop_move_mouse",
            description=(
                "把鼠标光标移动到屏幕坐标 (x, y) 但不点击。用于悬停展开菜单、"
                "或在滚动/拖拽前把光标定位到目标区域。坐标通常来自 desktop_list_elements "
                "返回的元素 center。"
            ),
            parameters={"type": "object", "properties": dict(_COORDS), "required": ["x", "y"]},
            handler=lambda a: (bot.move_to(a["x"], a["y"]) or _ok(f"moved to ({a['x']}, {a['y']})")),
        ))

        self._add(ToolSpec(
            name="desktop_click",
            description=(
                "在屏幕绝对坐标 (x, y) 单击鼠标左键。优先使用 desktop_click_button "
                "按名字点击；只有在没有可识别控件（自绘界面/游戏）时才用坐标点击。"
            ),
            parameters={"type": "object", "properties": dict(_COORDS), "required": ["x", "y"]},
            handler=lambda a: (bot.click(a["x"], a["y"]) or _ok(f"left-clicked ({a['x']}, {a['y']})")),
        ))

        self._add(ToolSpec(
            name="desktop_double_click",
            description="在屏幕坐标 (x, y) 双击鼠标左键（如打开文件、选中单词）。",
            parameters={"type": "object", "properties": dict(_COORDS), "required": ["x", "y"]},
            handler=lambda a: (bot.double_click(a["x"], a["y"]) or _ok(f"double-clicked ({a['x']}, {a['y']})")),
        ))

        self._add(ToolSpec(
            name="desktop_right_click",
            description="在屏幕坐标 (x, y) 单击鼠标右键，通常用于弹出上下文菜单。",
            parameters={"type": "object", "properties": dict(_COORDS), "required": ["x", "y"]},
            handler=lambda a: (bot.right_click(a["x"], a["y"]) or _ok(f"right-clicked ({a['x']}, {a['y']})")),
        ))

        self._add(ToolSpec(
            name="desktop_middle_click",
            description="在屏幕坐标 (x, y) 单击鼠标中键（按下滚轮）。浏览器里常在新标签页打开链接。",
            parameters={"type": "object", "properties": dict(_COORDS), "required": ["x", "y"]},
            handler=lambda a: (bot.middle_click(a["x"], a["y"]) or _ok(f"middle-clicked ({a['x']}, {a['y']})")),
        ))

        self._add(ToolSpec(
            name="desktop_mouse_down",
            description=(
                "按下并按住鼠标键（不松开）。配合 desktop_mouse_up 可实现拖拽、框选、长按。"
                "可选 x,y：给出时先把光标移过去再按下。button 默认 left。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "button": _MOUSE_BTN,
                    "x": {"type": "integer", "description": "可选横坐标，给出则先移动再按下。"},
                    "y": {"type": "integer", "description": "可选纵坐标，给出则先移动再按下。"},
                },
                "required": [],
            },
            handler=lambda a: self._mouse_down(a),
        ))

        self._add(ToolSpec(
            name="desktop_mouse_up",
            description=(
                "松开之前按住的鼠标键。通常与 desktop_mouse_down 配对使用。"
                "可选 x,y：给出则先移动到该处再松开。button 默认 left。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "button": _MOUSE_BTN,
                    "x": {"type": "integer", "description": "可选横坐标。"},
                    "y": {"type": "integer", "description": "可选纵坐标。"},
                },
                "required": [],
            },
            handler=lambda a: self._mouse_up(a),
        ))

        self._add(ToolSpec(
            name="desktop_scroll",
            description=(
                "滚动鼠标滚轮。direction 取 up/down（垂直）或 left/right（水平）。"
                "amount 是滚动格数（越大滚越多，默认 3）。滚轮作用于光标所在位置，"
                "所以滚动前可用 desktop_move_mouse 或传 x,y 把光标定位到目标区域。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "direction": _SCROLL_DIR,
                    "amount": {
                        "type": "integer",
                        "description": "滚动格数（正数），默认 3。",
                        "default": 3,
                    },
                    "x": {"type": "integer", "description": "可选横坐标，给出则先移到该处再滚。"},
                    "y": {"type": "integer", "description": "可选纵坐标，给出则先移到该处再滚。"},
                },
                "required": ["direction"],
            },
            handler=lambda a: self._scroll(a),
        ))

        self._add(ToolSpec(
            name="desktop_drag",
            description=(
                "按住鼠标左键从 (x1,y1) 拖到 (x2,y2) 后松开。用于移动窗口、滑块、"
                "拖拽文件、框选。需要更细粒度控制时改用 desktop_mouse_down/mouse_up。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "x1": {"type": "integer", "description": "起点横坐标。"},
                    "y1": {"type": "integer", "description": "起点纵坐标。"},
                    "x2": {"type": "integer", "description": "终点横坐标。"},
                    "y2": {"type": "integer", "description": "终点纵坐标。"},
                },
                "required": ["x1", "y1", "x2", "y2"],
            },
            handler=lambda a: (
                bot.drag(a["x1"], a["y1"], a["x2"], a["y2"])
                or _ok(f"dragged ({a['x1']},{a['y1']})->({a['x2']},{a['y2']})")
            ),
        ))

        # ---- 键盘 ----------------------------------------------------- #
        self._add(ToolSpec(
            name="desktop_type_text",
            description=(
                "在当前键盘焦点处逐字输入文本（支持中文等 Unicode）。"
                "注意：调用前必须先用 desktop_click / desktop_click_button / desktop_type_into "
                "把焦点放到目标输入框，否则文字会输到错误的地方。需要往指定字段填值时优先用 desktop_type_into。"
            ),
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string", "description": "要输入的文本。"}},
                "required": ["text"],
            },
            handler=lambda a: (bot.type_text(a["text"]) or _ok(f"typed {a['text']!r}")),
        ))

        self._add(ToolSpec(
            name="desktop_key_press",
            description=(
                "按键或组合键。单键如 'enter'、'tab'、'esc'、'delete'、'f5'；"
                "组合键用 '+' 连接，如 'ctrl+c'、'ctrl+v'、'alt+f4'、'ctrl+shift+esc'。"
                "修饰键别名：control/cmd/windows 会自动归一化。"
            ),
            parameters={
                "type": "object",
                "properties": {"key": {"type": "string", "description": "键名或 '+' 连接的组合键。"}},
                "required": ["key"],
            },
            handler=lambda a: (bot.key_press(a["key"]) or _ok(f"pressed {a['key']!r}")),
        ))

        # ---- 语义动作 ------------------------------------------------- #
        self._add(ToolSpec(
            name="desktop_click_button",
            description=(
                "在指定窗口内按名字找到按钮并点击（无需坐标，最稳）。"
                "匹配 Button / MenuItem / Link / RadioButton。window 传窗口 id 或标题子串。"
                "这是点击**标准 UI** 按钮的首选方式。"
                "注意：若目标应用是自绘界面（微信、游戏、Canvas、部分 Electron），"
                "UIA 读不到按钮，请改用 desktop_find_text_click（OCR 按文字定位点击）。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "window": _window_param(),
                    "name": {"type": "string", "description": "按钮名字。"},
                    "exact": {
                        "type": "boolean",
                        "description": "名字是否精确匹配（大小写不敏感），false 为子串包含。默认 true。",
                        "default": True,
                    },
                    "index": {
                        "type": "integer",
                        "description": "同名按钮有多个时选第几个（从 0 开始）。",
                        "default": 0,
                    },
                },
                "required": ["window", "name"],
            },
            handler=lambda a: self._click_button(a),
        ))

        self._add(ToolSpec(
            name="desktop_click_text",
            description=(
                "点击指定窗口内名字包含某段文本的任意可见元素（不限控件类型，"
                "适合点链接、标签、列表项等非按钮控件）。window 传窗口 id 或标题子串。"
                "用于**标准 UI**。自绘界面（微信/游戏/Canvas）UIA 读不到元素名时，"
                "改用 desktop_find_text_click（OCR 定位文字点击）。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "window": _window_param(),
                    "text": {"type": "string", "description": "要匹配并点击的文本。"},
                    "index": {"type": "integer", "description": "多个匹配时选第几个。", "default": 0},
                },
                "required": ["window", "text"],
            },
            handler=lambda a: self._click_text(a),
        ))

        self._add(ToolSpec(
            name="desktop_type_into",
            description=(
                "在指定窗口里按标签找到输入框，点击聚焦、清空，然后填入文本。"
                "这是往表单字段填值的首选（自动处理焦点和清空）。window 传窗口 id 或标题子串，"
                "field 是输入框标签/名字包含的子串。需要 OCR 兜底（自绘界面）时用 desktop_find_text。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "window": _window_param(),
                    "field": {"type": "string", "description": "输入框标签/名字包含的子串。"},
                    "text": {"type": "string", "description": "要填入的文本。"},
                    "clear": {
                        "type": "boolean",
                        "description": "填入前是否清空已有内容（Ctrl+A + Delete）。默认 true。",
                        "default": True,
                    },
                },
                "required": ["window", "field", "text"],
            },
            handler=lambda a: self._type_into(a),
        ))

        self._add(ToolSpec(
            name="desktop_fill_form",
            description=(
                "在指定窗口批量填表：fields 是 {字段标签: 值} 的映射，依次对每个字段调用 desktop_type_into。"
                "window 传窗口 id 或标题子串。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "window": _window_param(),
                    "fields": {
                        "type": "object",
                        "description": "字段标签到值的映射，例如 {\"用户名\": \"alice\", \"密码\": \"***\"}。",
                        "additionalProperties": {"type": "string"},
                    },
                    "clear": {"type": "boolean", "description": "填入前是否清空，默认 true。", "default": True},
                },
                "required": ["window", "fields"],
            },
            handler=lambda a: self._fill_form(a),
        ))

        # ---- 等待 ----------------------------------------------------- #
        self._add(ToolSpec(
            name="desktop_wait_for",
            description=(
                "轮询等待某个元素出现（用于页面加载、弹窗、操作结果反馈）。"
                "传 text 等待名字包含该子串的元素，或 name 精确匹配。可限定 window。"
                "超时返回错误（不抛异常）。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "等待元素名字包含的子串。"},
                    "name": {"type": "string", "description": "等待元素的精确名字。"},
                    "window": _window_param("可选：只在该窗口内查找。"),
                    "timeout": {"type": "number", "description": "最长等待秒数。", "default": 10},
                    "poll_interval": {"type": "number", "description": "轮询间隔秒数。", "default": 0.5},
                },
                "required": [],
            },
            handler=lambda a: self._wait_for(a),
        ))

        self._add(ToolSpec(
            name="desktop_wait_until_gone",
            description=(
                "轮询等待某个元素消失（用于等待加载遮罩关闭、弹窗消失）。"
                "传 text 或 name，可限定 window。超时返回错误。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "等待消失元素名字包含的子串。"},
                    "name": {"type": "string", "description": "等待消失元素的精确名字。"},
                    "window": _window_param("可选：只在该窗口内查找。"),
                    "timeout": {"type": "number", "description": "最长等待秒数。", "default": 10},
                    "poll_interval": {"type": "number", "description": "轮询间隔秒数。", "default": 0.5},
                },
                "required": [],
            },
            handler=lambda a: self._wait_until_gone(a),
        ))

        # ---- OCR（视觉兜底）----------------------------------------- #
        self._add(ToolSpec(
            name="desktop_find_text",
            description=(
                "用 OCR 在屏幕（或指定区域）上定位文字，返回匹配位置矩形列表。"
                "用于自绘界面（微信某些区域、游戏、Canvas）这类 UIA 控件树读不到文字的场景。"
                "需要安装 tesseract 并启用 [ocr] 依赖。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "要查找的文字。"},
                    "region": {
                        "type": "array",
                        "description": "可选搜索区域 [left, top, right, bottom]（屏幕坐标）。",
                        "items": {"type": "integer"},
                        "minItems": 4,
                        "maxItems": 4,
                    },
                    "lang": {
                        "type": "string",
                        "description": "OCR 语言，默认 chi_sim+eng（简体中文+英文）。",
                        "default": "chi_sim+eng",
                    },
                },
                "required": ["text"],
            },
            handler=lambda a: self._find_text(a),
        ))

        self._add(ToolSpec(
            name="desktop_find_text_click",
            description=(
                "用 OCR 定位指定文字并直接点击其中心。**这是自绘界面（微信、游戏、Canvas、"
                "部分 Electron）点击的首选工具**——这类应用 UIA 读不到按钮，click_button / "
                "click_text 会找不到控件。用法：你只要说点哪个字（如『搜索』『发送』），"
                "它负责找到并点下去。找不到或 index 越界返回可理解的错误。"
                "需要 tesseract + [ocr] 依赖。可选 window：给出则先激活该窗口再点。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "要找到并点击的文字。"},
                    "window": _window_param(
                        "可选：目标窗口 id 或标题子串，给出则先激活该窗口再点击（防止点错应用）。"
                    ),
                    "region": {
                        "type": "array",
                        "description": "可选搜索区域 [left, top, right, bottom]（屏幕坐标）。",
                        "items": {"type": "integer"},
                        "minItems": 4,
                        "maxItems": 4,
                    },
                    "index": {
                        "type": "integer",
                        "description": "多个匹配时点第几个（从 0 开始）。",
                        "default": 0,
                    },
                    "lang": {
                        "type": "string",
                        "description": "OCR 语言，默认 chi_sim+eng。",
                        "default": "chi_sim+eng",
                    },
                },
                "required": ["text"],
            },
            handler=lambda a: self._find_text_click(a),
        ))

        self._add(ToolSpec(
            name="desktop_wait_for_text",
            description=(
                "用 OCR 轮询等待某段文字在屏幕（或区域）上出现，出现后返回其位置矩形。"
                "用于自绘界面（微信/游戏/Canvas）的加载等待：等某个文字（如『已发送』、"
                "『加载完成』）出现再继续。超时抛 WaitTimeoutError。需要 tesseract + [ocr]。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "要等待出现的文字。"},
                    "region": {
                        "type": "array",
                        "description": "可选搜索区域 [left, top, right, bottom]。",
                        "items": {"type": "integer"},
                        "minItems": 4,
                        "maxItems": 4,
                    },
                    "timeout": {"type": "number", "description": "最长等待秒数。", "default": 10},
                    "poll_interval": {"type": "number", "description": "轮询间隔秒数。", "default": 1.0},
                    "lang": {"type": "string", "description": "OCR 语言。", "default": "chi_sim+eng"},
                },
                "required": ["text"],
            },
            handler=lambda a: self._wait_for_text_ocr(a),
        ))

        self._add(ToolSpec(
            name="desktop_wait_until_text_gone",
            description=(
                "用 OCR 轮询等待某段文字消失（如加载遮罩、弹窗文字）。"
                "用于自绘界面等待操作完成。超时抛 WaitTimeoutError。需要 tesseract + [ocr]。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "要等待消失的文字。"},
                    "region": {
                        "type": "array",
                        "description": "可选搜索区域 [left, top, right, bottom]。",
                        "items": {"type": "integer"},
                        "minItems": 4,
                        "maxItems": 4,
                    },
                    "timeout": {"type": "number", "description": "最长等待秒数。", "default": 10},
                    "poll_interval": {"type": "number", "description": "轮询间隔秒数。", "default": 1.0},
                    "lang": {"type": "string", "description": "OCR 语言。", "default": "chi_sim+eng"},
                },
                "required": ["text"],
            },
            handler=lambda a: self._wait_until_text_gone_ocr(a),
        ))

    # ------------------------------------------------------------------ #
    # 各 handler 实现
    # ------------------------------------------------------------------ #
    def _win(self, ref: Any) -> Window:
        return self._resolve_window(ref)

    def _screenshot(self, a: dict[str, Any]):
        from ..vision.screenshot import screenshot_b64

        max_kb = int(a.get("max_size_kb", 500))
        # 同时拿原始 PNG 用于图像 content，b64(JPEG) 放在结果里给 LLM。
        raw_png = self._bot.screenshot()
        b64 = screenshot_b64(self._bot._platform, max_size_kb=max_kb)
        value = {"image_base64": b64, "mime_type": "image/jpeg", "bytes_b64": len(b64)}
        # 图像 content 用 JPEG（体积小），重新生成一份字节。
        import base64

        jpeg_bytes = base64.b64decode(b64)
        return value, jpeg_bytes, "image/jpeg"

    def _list_elements(self, a: dict[str, Any]):
        win = self._win(a["window"])
        roots = self._bot.list_elements(window=win)
        out: list[dict[str, Any]] = []
        for root in roots:
            for el in root.walk():
                if el.visible:
                    out.append(_element_brief(el))
        return out

    def _mouse_down(self, a: dict[str, Any]):
        button = a.get("button", "left")
        x, y = a.get("x"), a.get("y")
        self._bot.mouse_down(button=button, x=x, y=y)
        return _ok(f"pressed {button}")

    def _mouse_up(self, a: dict[str, Any]):
        button = a.get("button", "left")
        x, y = a.get("x"), a.get("y")
        self._bot.mouse_up(button=button, x=x, y=y)
        return _ok(f"released {button}")

    def _scroll(self, a: dict[str, Any]):
        direction = a["direction"]
        amount = int(a.get("amount", 3))
        x, y = a.get("x"), a.get("y")
        self._bot.scroll(direction, amount=amount, x=x, y=y)
        return _ok(f"scrolled {direction} {amount}")

    def _click_button(self, a: dict[str, Any]):
        from ..actions.click import click_button

        win = self._win(a["window"])
        el = click_button(
            self._bot._platform,
            win,
            name=a["name"],
            exact=a.get("exact", True),
            index=a.get("index", 0),
        )
        return {"clicked": _element_brief(el)}

    def _click_text(self, a: dict[str, Any]):
        from ..actions.click import click_text

        win = self._win(a["window"])
        el = click_text(self._bot._platform, win, text=a["text"], index=a.get("index", 0))
        return {"clicked": _element_brief(el)}

    def _type_into(self, a: dict[str, Any]):
        from ..actions.type_text import type_into

        win = self._win(a["window"])
        el = type_into(
            self._bot._platform,
            win,
            field=a["field"],
            text=a["text"],
            clear=a.get("clear", True),
        )
        return {"filled": _element_brief(el)}

    def _fill_form(self, a: dict[str, Any]):
        from ..actions.form import fill_form

        win = self._win(a["window"])
        result = fill_form(
            self._bot._platform, win, fields=a["fields"], clear=a.get("clear", True)
        )
        return {
            "filled": [
                {"field": field, "element": _element_brief(el)}
                for field, el in result.items()
            ]
        }

    def _wait_for(self, a: dict[str, Any]):
        from ..actions.wait import wait_for

        win = self._win(a["window"]) if a.get("window") else None
        el = wait_for(
            self._bot._platform,
            text=a.get("text"),
            name=a.get("name"),
            window=win,
            timeout=float(a.get("timeout", 10)),
            poll_interval=float(a.get("poll_interval", 0.5)),
        )
        return {"found": _element_brief(el)}

    def _wait_until_gone(self, a: dict[str, Any]):
        from ..actions.wait import wait_until_gone

        win = self._win(a["window"]) if a.get("window") else None
        wait_until_gone(
            self._bot._platform,
            text=a.get("text"),
            name=a.get("name"),
            window=win,
            timeout=float(a.get("timeout", 10)),
            poll_interval=float(a.get("poll_interval", 0.5)),
        )
        return _ok("element gone")

    def _find_text(self, a: dict[str, Any]):
        from ..core.types import Rect
        from ..vision.ocr import find_text

        region = a.get("region")
        rect = Rect(*region) if region else None
        rects = find_text(
            self._bot._platform,
            text=a["text"],
            region=rect,
            lang=a.get("lang", "chi_sim+eng"),
        )
        return {"matches": [r.to_tuple() for r in rects]}

    def _find_text_click(self, a: dict[str, Any]):
        """OCR 定位文字并点击其中心（自绘界面首选操作）。"""
        from ..core.exceptions import ElementNotFoundError
        from ..core.types import Rect
        from ..vision.ocr import find_text

        region = a.get("region")
        rect = Rect(*region) if region else None
        rects = find_text(
            self._bot._platform,
            text=a["text"],
            region=rect,
            lang=a.get("lang", "chi_sim+eng"),
        )
        if not rects:
            raise ElementNotFoundError(
                f"OCR 在当前画面里没找到文字 {a['text']!r}",
                details={
                    "text": a["text"],
                    "searched_region": rect.to_tuple() if rect else "fullscreen",
                },
            )
        idx = int(a.get("index", 0))
        if idx < 0 or idx >= len(rects):
            raise ElementNotFoundError(
                f"OCR 找到 {len(rects)} 个匹配，但 index={idx} 越界",
                details={"text": a["text"], "count": len(rects), "index": idx},
            )

        target = rects[idx]
        # 可选：先激活目标窗口，防止点进其它应用。
        win_ref = a.get("window")
        if win_ref is not None:
            win = self._resolve_window(win_ref)
            hwnd = getattr(win, "hwnd", None)
            activator = getattr(self._bot._platform, "_activate_window", None)
            if hwnd and callable(activator):
                activator(hwnd)

        cx, cy = target.center.to_tuple()
        self._bot._platform.click(cx, cy)
        return {
            "clicked": {
                "text": a["text"],
                "rect": target.to_tuple(),
                "center": [cx, cy],
                "total_matches": len(rects),
            }
        }

    def _wait_for_text_ocr(self, a: dict[str, Any]):
        """OCR 轮询等待某段文字出现。"""
        import time

        from ..core.exceptions import WaitTimeoutError
        from ..core.types import Rect
        from ..vision.ocr import find_text

        text = a["text"]
        region = a.get("region")
        rect = Rect(*region) if region else None
        timeout = float(a.get("timeout", 10))
        poll = float(a.get("poll_interval", 1.0))
        lang = a.get("lang", "chi_sim+eng")

        deadline = time.monotonic() + timeout
        last_matches = 0
        while True:
            matches = find_text(self._bot._platform, text=text, region=rect, lang=lang)
            last_matches = len(matches)
            if matches:
                return {
                    "found": {
                        "text": text,
                        "rect": list(matches[0].to_tuple()),
                        "matches": last_matches,
                    }
                }
            if time.monotonic() >= deadline:
                break
            time.sleep(poll)

        raise WaitTimeoutError(
            f"OCR 等待 {timeout:.1f}s 后文字 {text!r} 仍未出现",
            details={"text": text, "timeout": timeout, "last_matches": last_matches},
        )

    def _wait_until_text_gone_ocr(self, a: dict[str, Any]):
        """OCR 轮询等待某段文字消失。"""
        import time

        from ..core.exceptions import WaitTimeoutError
        from ..core.types import Rect
        from ..vision.ocr import find_text

        text = a["text"]
        region = a.get("region")
        rect = Rect(*region) if region else None
        timeout = float(a.get("timeout", 10))
        poll = float(a.get("poll_interval", 1.0))
        lang = a.get("lang", "chi_sim+eng")

        deadline = time.monotonic() + timeout
        last_matches = 1
        while True:
            matches = find_text(self._bot._platform, text=text, region=rect, lang=lang)
            last_matches = len(matches)
            if not matches:
                return {"gone": {"text": text}}
            if time.monotonic() >= deadline:
                break
            time.sleep(poll)

        raise WaitTimeoutError(
            f"OCR 等待 {timeout:.1f}s 后文字 {text!r} 仍存在（匹配 {last_matches} 处）",
            details={"text": text, "timeout": timeout, "last_matches": last_matches},
        )


def _ok(message: str) -> dict[str, str]:
    """成功但无结构化数据时的简短返回。"""
    return {"status": "ok", "message": message}
