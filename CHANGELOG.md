# Changelog

本项目遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Docs — 文档

- README 补滞到 v0.2.1 实际状态：结构图补 `tools/` 注册表与 MCP server；
  新增「统一工具注册表 + MCP / 接入 Hermes」小节；验收清单按实测勾选
  （basic_usage / open_browser / 单测 / 集成测试 / 高 DPI 坐标闭环 / Hermes 22 工具）；
  路线图标注 v0.1–v0.2.1 完成状态。

## v0.2.1 — 修复 Hermes 工具调用 + 高 DPI 点击错位

两个在真实 Hermes 联调中暴露的 bug 修复。

### Fixed — 修复

- **MCP server 与 mcp 2.0 不兼容导致 Hermes 调用工具必崩**：`desktop-pilot[mcp]`
  的依赖约束写成了 `mcp>=1.0`，安装时把 mcp 拉到了 2.0.0；但 Hermes 自身 pin
  的是 `mcp==1.26.0`，其客户端按 1.x 访问 `CallToolResult.isError`，而 2.0
  把该字段改名为 `is_error`，于是**列工具正常、一调用就抛
  `'CallToolResult' object has no attribute 'isError'`**。server 改用 mcp 1.x
  的装饰器 API（`@server.list_tools()` / `@server.call_tool()`，
  `inputSchema` / `isError`），并把依赖收紧为 `mcp>=1.0,<2.0`，与宿主一致。
- **高 DPI 缩放下截图坐标与点击坐标错位（"看得清却点不准"）**：Windows 后端
  此前没有声明 DPI 感知。在 125% 缩放（DPI 120）的机器上，非感知进程被系统
  位图缩放，截图 / pywinauto(UIA) 控件 rect / pyautogui 点击落在两套坐标系
  （逻辑 1536×864 vs 物理 1920×1080），点击整体偏移。现在模块导入时即调用
  `_enable_dpi_awareness()`（Per-Monitor V2 → V1 → System 逐级降级），三者
  统一到物理像素。
- 修正 `[project.scripts]` 段误放 `dev` 依赖列表导致源码构建失败的问题
  （`project.scripts.dev must be string`）。

## v0.2.0 — 统一 Agent API + MCP + 完整鼠标

面向 AI agent 的接口层重写：引入**工具注册表**作为所有工具的唯一真相源，
新增 **MCP server**，并把鼠标能力补全到左/右/中键 + 滚轮 + 按下/松开。
0.x 阶段 Platform ABC 新增抽象方法按 MINOR 递增。

### Added — 新增

- **工具注册表** (`tools/`)：`ToolSpec`（名字/描述/JSON schema/handler 绑定）
  和 `ToolRegistry`，是所有 agent 集成的唯一真相源。22 个工具只在此定义一次，
  OpenAI function-calling / LangChain / MCP 全部从它自动派生，杜绝多份定义漂移。
  - `ToolRegistry.openai_schema()`、`.mcp_tools()`、`.call(name, args)` 统一分发。
  - `ToolResult` 统一返回包络：`{ok, result|error, image}`，所有异常在分发边界
    被捕获成结构化错误，不再让 agent loop 崩溃。
  - **窗口 id 寻址**：窗口工具的 `window` 参数既接受标题子串，也接受
    `list_windows` 返回的窗口 id（hwnd 字符串），解决重名窗口/句柄无法回传的问题。
- **完整鼠标 API**（Platform / Desktop / Windows 后端 + 注册表工具）：
  - `move_to(x, y)`：移动光标不按键（悬停/定位）。
  - `middle_click(x, y)`：中键（滚轮按下）单击。
  - `mouse_down(button, x?, y?)` / `mouse_up(button, x?, y?)`：按下/松开原子操作，
    支持 `left/right/middle`，可自定义拖拽、框选、长按。
  - `scroll(direction, amount, x?, y?)`：滚轮支持先把光标定位到目标区域再滚
    （滚轮作用于光标所在控件），水平滚动保留 hscroll/shift+滚轮兜底。
  - 新增工具：`desktop_move_mouse`、`desktop_double_click`、`desktop_middle_click`、
    `desktop_mouse_down`、`desktop_mouse_up`、`desktop_scroll`、`desktop_drag`、
    `desktop_click_text`、`desktop_fill_form`、`desktop_find_text`（OCR）、
    `desktop_wait_until_gone`（工具集从 10 扩充到 22）。
- **MCP server** (`integrations/mcp_server.py`)：stdio 传输，一个
  `desktop-pilot-mcp` 控制台入口（`python -m desktop_pilot.integrations.mcp_server`）。
  工具列表与调用全部从注册表派生，已用真实 MCP client 端到端验证。
- `integrations.function_call.call_tool(name, args, desktop)`：原生 function-calling
  的执行器，拿到模型 tool_call 后直接分发，无需手写 if/else。

### Changed — 变更

- `integrations/function_call.py` 与 `integrations/langchain.py` 改为从注册表派生
  的薄封装；`get_tools_schema(desktop=None)` 与 `get_tools(desktop)` 签名向后兼容。
- LangChain 工具改用 `StructuredTool` + 动态 pydantic 模型，参数 schema 与注册表同源。
- 版本号升至 **0.2.0**。

### Fixed — 修复

- Windows 后端每次鼠标/键盘操作前重新确认前台窗口（`_ensure_foreground`），
  修复在 Hermes CLI 等会频繁抢焦点的环境下 SendInput 被路由到错误应用的问题。
- `scroll` 现在会先激活/定位，保证滚动落到目标窗口。

## v0.1.0 — 初始 MVP

首个可用版本，完成 README 任务清单 T01–T24 的全部 P0–P4 任务。

### Added — 新增

- **核心类型** (`core/types.py`)：`Point` / `Size` / `Rect`，`frozen=True` 不可变，
  提供 `center`、`contains`、`to_tuple`。
- **异常体系** (`core/exceptions.py`)：`DesktopPilotError` 基类 +
  `ElementNotFoundError` / `WindowNotFoundError` / `WaitTimeoutError` /
  `PlatformError` / `UnsupportedOperationError`，每个异常带可选 `details` 字典。
  超时异常刻意命名为 `WaitTimeoutError`，避免遮蔽内置 `TimeoutError`。
- **元素模型** (`core/element.py`)：`Element` / `Control` / `Window`、
  `ControlType` 枚举、`find_child()` / `walk()` / `to_dict()`。
- **平台抽象** (`core/platform.py`)：`Platform` ABC，定义 12 个平台后端必须实现的方法。
- **Windows 后端** (`platforms/windows.py`)：基于 pywinauto(UIA) + PyAutoGUI，
  枚举窗口、读取控件树、坐标点击、拖拽、滚动、按键、截图。
  - `_activate_window` 用 `AttachThreadInput` 绕过 Windows 对 `SetForegroundWindow` 的限制。
  - 控件树通过 `descendants()` 递归转成 `Element`。
- **顶层 `Desktop` API** (`__init__.py`)：自动检测平台、context manager、
  代理底层方法，并暴露语义动作 `click_button` / `click_text` / `type_into` /
  `wait_for` / `wait_until_gone` / `fill_form` / `find_text`。
- **Agent 友好层** (`actions/`)：
  - `click.py`：按名字点按钮 / 点含某文本的元素，自动点控件中心。
  - `type_text.py`：按标签找输入框、点击聚焦、清空、输入。
  - `wait.py`：轮询等待元素出现/消失，支持窗口内限定。
  - `form.py`：批量填表。
- **视觉兜底** (`vision/`)：
  - `screenshot.py`：base64 JPEG 截图（自动按 80→60→40→25 降质量压缩）、存盘。
  - `ocr.py`：pytesseract OCR 定位屏幕文字，支持区域裁剪与坐标偏移。
- **框架集成** (`integrations/`)：
  - `function_call.py`：10 个 OpenAI/Anthropic 兼容的 function-calling schema。
  - `langchain.py`：10 个 `BaseTool`，`get_tools(desktop)` 绑定到 Desktop 实例。
- **跨平台占位**：macOS / Linux 后端接口对齐，所有方法抛 `UnsupportedOperationError`，
  `close()` 为 no-op 以便 context manager 干净退出。
- **示例**：`basic_usage.py`、`open_browser.py`、`langchain_agent.py`。
- **文档**：`docs/getting_started.md`（10 分钟教程）、`docs/api_reference.md`、
  `CONTRIBUTING.md`。
- **测试**：90 个单元测试（mock `Platform`，不依赖真实 GUI，覆盖率 89%）+
  3 个真实 Windows 集成测试（`@pytest.mark.integration`）。

### Fixed — 修复

- **Windows 后端中文/Unicode 输入丢失**：`pyautogui.write()` 在 Windows 上只能输入
  ASCII，中文被静默丢弃。改为对非 ASCII 字符走 Win32 `SendInput` +
  `KEYEVENTF_UNICODE`，支持中文、带重音字母、BMP 外字符（emoji 用 UTF-16 代理对）。
  同时修正两个会让 `SendInput` 在 64 位下静默失败的问题：
  1. `INPUT` 联合体必须包含最大的 `MOUSEINPUT` 成员，使 `sizeof(INPUT)` = 原生 40
     字节（之前只有 `KEYBDINPUT`，结构体偏小被系统拒绝）。
  2. 必须声明 `SendInput.argtypes`，否则 64 位下 `LPINPUT` 指针被截断；
     `dwExtraInfo` 用 `c_void_p`（`ULONG_PTR` 宽度）而非定长类型。
  `SendInput` 返回 0 时现在抛 `PlatformError`，不再静默丢字。
- **窗口 `pid` 始终为 `None`**：`pywin32` 的 `GetWindowThreadProcessId` 不在
  `win32gui` 而在 `win32process`/直接 user32 调用；改用
  `user32.GetWindowThreadProcessId(hwnd, &lpdw)` 正确取进程 id。
- **`open_browser.py` 示例逻辑错误**：原示例把 `wait_for(text="Chrome")` 返回的
  `Element` 当 `Window` 用。改为直接轮询 `find_window`，并用 `Ctrl+L`
  聚焦地址栏（比按名字找自绘地址栏控件更稳）。
