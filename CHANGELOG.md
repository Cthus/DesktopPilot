# Changelog

本项目遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### v0.1.0 — 初始 MVP

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
