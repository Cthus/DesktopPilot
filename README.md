# DesktopPilot

**给 AI agent 用的 Windows 桌面图形化编程 SDK。**

让 LLM agent 能"看见"窗口结构、按语义操作控件（按名字点按钮、读输入框、等元素出现），而不是靠坐标盲点。
类似 Anthropic Computer Use 的能力，但走结构化路径，速度更快、更稳。

---

## 为什么需要这个

现在 AI 操作桌面只有两条路：

| 方案 | 问题 |
|---|---|
| **PyAutoGUI 坐标点击** | 改分辨率/窗口移动就废，AI 也记不住坐标 |
| **截图 → GPT-4V 决策** | 慢（秒级）、贵、坐标会漂、按钮视觉歧义 |

DesktopPilot 走第三条路：**直接读 Windows UIA 控件树**，拿到结构化数据：

```
Window: "微信 - 文件传输助手"
  ├─ Edit: "" (输入框) @ (850, 400)
  ├─ Button: "发送" @ (920, 400)
  └─ List: [消息列表]
```

AI 拿到的是 `click_button("发送")` 这种语义调用，不是 `(920, 400)`。

---

## 项目结构

```
DesktopPilot/
├── pyproject.toml              # 包配置，pip install -e .
├── README.md                   # 本文件
├── LICENSE                     # MIT
├── src/
│   └── desktop_pilot/
│       ├── __init__.py         # 公开 API 入口
│       ├── py.typed            # 类型标记
│       ├── core/               # 核心抽象层（平台无关）
│       │   ├── platform.py     # Platform 抽象基类
│       │   ├── element.py      # Element / Window / Control 数据类
│       │   ├── exceptions.py   # 异常体系
│       │   └── types.py        # Rect, Point 等基础类型
│       ├── platforms/          # 平台实现
│       │   ├── windows.py      # Windows 后端（UIA + PyAutoGUI）
│       │   ├── macos.py        # macOS stub（占位，抛 NotImplementedError）
│       │   └── linux.py        # Linux stub（占位）
│       ├── vision/             # 视觉/OCR 兜底
│       │   ├── ocr.py          # pytesseract 文字识别
│       │   └── screenshot.py   # 截图 + base64 编码
│       ├── actions/            # 高级语义动作（agent 友好）
│       │   ├── click.py        # click_button / click_text
│       │   ├── type_text.py    # type_into / type_at
│       │   ├── wait.py         # wait_for / wait_until_gone
│       │   └── form.py         # fill_form 批量填表
│       ├── tools/              # 统一工具注册表（所有 agent 集成的唯一真相源）
│       │   ├── spec.py         # ToolSpec / ToolResult / 错误分类
│       │   └── registry.py     # ToolRegistry：22 个工具只定义一次
│       └── integrations/       # 第三方框架适配
│           ├── function_call.py # OpenAI Function Calling schema
│           ├── langchain.py     # LangChain Tool 包装
│           └── mcp_server.py    # MCP stdio server（desktop-pilot-mcp）
├── tests/                      # 测试
│   ├── unit/                   # mock 平台单测
│   └── integration/            # 真实 Windows 集成测试（@pytest.mark.integration）
└── examples/                   # 示例
    ├── basic_usage.py          # 5 行跑起来
    ├── open_browser.py         # "打开浏览器搜 Python"
    └── langchain_agent.py      # 接 LangChain agent
```

---

## 核心 API（agent 视角）

```python
from desktop_pilot import Desktop

with Desktop() as bot:
    # 感知
    bot.screenshot()                     # -> base64 PNG
    bot.list_windows()                   # -> [Window, ...]
    bot.find_window(title="微信")
    win = bot.find_window(title_contains="文件传输")
    bot.list_elements(window=win)        # -> 控件树

    # 动作
    bot.click(x=100, y=200)
    bot.click_button(window=win, name="发送")
    bot.type_text("hello")
    bot.type_into(window=win, field="输入框", text="admin")
    bot.key_press("enter")
    bot.scroll("down", amount=3)

    # 高级（agent 最常用）
    bot.wait_for(text="加载完成", timeout=10)
    bot.wait_for(window=win, name="确定", timeout=5)
    bot.fill_form(window=win, fields={"用户名": "admin", "密码": "123"})
```

---

## 给 agent 用：统一工具注册表 + MCP

所有 agent 集成共用同一份工具定义——[`tools/Registry`](src/desktop_pilot/tools/registry.py) 是**唯一真相源**，
25 个工具（感知 / 全套鼠标 / 键盘 / 语义点击 / 等待 / OCR / 自绘界面专用）只定义一次，
OpenAI Function Calling、LangChain、MCP 全部自动派生，杜绝多份定义漂移：

```python
from desktop_pilot import Desktop
from desktop_pilot.tools import ToolRegistry

reg = ToolRegistry(Desktop())
reg.names()          # 25 个工具名
reg.openai_schema()  # OpenAI function-calling schema
reg.mcp_tools()      # MCP Tool 列表
reg.call("desktop_click_button", {"window": "微信", "name": "发送"})
```

### 接入 Hermes（已配置好）

本地 Hermes 通过 stdio MCP server 使用这套工具，
已在 `C:\Users\Administrator\AppData\Local\hermes\config.yaml` 注册：

```yaml
mcp_servers:
  desktop-pilot:
    command: <hermes-venv-python>
    args: [-m, desktop_pilot.integrations.mcp_server]
    enabled: true
```

Hermes 里的工具名形如 `mcp_desktop_pilot_click_button`。验证：`hermes mcp test desktop-pilot`。
（注意：desktop-pilot 依赖用 `mcp>=1.0,<2.0` 与 Hermes 锁的 `mcp==1.26.0` 对齐，避免 2.0 的
`isError → is_error` 字段改名让 Hermes 调用崩溃。）

### 自绘界面（微信 / 游戏 / Canvas）怎么操作

微信、游戏、Canvas、部分 Electron 应用是**自绘界面**——UIA 控件树读不到按钮，
`desktop_click_button` / `desktop_click_text` 会找不到控件。请走 OCR 专用工具：

| 目标 | 用哪个工具 |
|---|---|
| 按文字点一下（搜索、发送） | `desktop_find_text_click`（定位即点击，首选） |
| 只定位文字位置 | `desktop_find_text` |
| 等某段文字出现 | `desktop_wait_for_text` |
| 等某段文字消失（加载遮罩） | `desktop_wait_until_text_gone` |

OCR 需要两层依赖：Python 包（`pip install 'desktop-pilot[ocr]'`）+ 系统 Tesseract 引擎
（Windows 装 [UB-Mannheim Tesseract](https://github.com/UB-Mannheim/tesseract/wiki)，或设
`TESSERACT_CMD` 指向 tesseract.exe）。引擎缺失时这些工具会抛**可操作**的
`OCRUnavailableError`（details 里明确缺什么、怎么装），而不是裸崩溃。

### 错误诊断

工具调用失败时返回结构化错误：`error.context.arguments` 带当时参数、
`error.details.env` 带失败瞬间的环境快照（屏幕/DPI 缩放/前台窗口/光标/版本）、
意外异常自带完整 `error.traceback`。排障时开全量日志（Hermes 会写入
`mcp-stderr.log`）：

```bash
export DESKTOP_PILOT_DEBUG=1     # Windows: set DESKTOP_PILOT_DEBUG=1
```

设了之后，预期错误也会附带完整调用栈，方便直接定位到源码行。

---

## 任务清单

**重要：每项任务都有完整的"目标 + 验收标准 + 实现提示 + 依赖项"。新 agent 拿 README 就开干。**

### 优先级说明
- **P0**：核心 MVP，必须先有，没有 P0 啥都跑不起来
- **P1**：Agent 友好层，让 SDK 对 LLM 好用
- **P2**：框架集成，接 LangChain / OpenAI
- **P3**：跨平台 stub，macOS / Linux 占位
- **P4**：收尾打磨，测试 + 文档

**完成顺序：T01 → T02 → T03 → T04 → T05 → T06 → T07 → T08 → T09 → ...**

---

### P0 — 核心 MVP

#### T01 — 基础类型 `core/types.py`

**目标**：定义 Rect / Point / Size 三个 dataclass，是所有几何计算的基石。

**验收标准**：
- [ ] `src/desktop_pilot/core/types.py` 文件存在
- [ ] `Point` 有 x, y 属性（int）+ `to_tuple()` 方法
- [ ] `Size` 有 width, height 属性 + `to_tuple()` 方法
- [ ] `Rect` 有 left, top, right, bottom 属性 + `center` 属性 + `contains(point)` 方法 + `to_tuple()` 方法
- [ ] 所有类都用 `@dataclass(frozen=True)`，不可变
- [ ] `from tests/unit/test_types.py` 跑通（5 个测试）

**实现提示**：
```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Point:
    x: int
    y: int
    def to_tuple(self) -> tuple[int, int]: ...

@dataclass(frozen=True)
class Size:
    width: int
    height: int
    def to_tuple(self) -> tuple[int, int]: ...

@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int
    @property
    def center(self) -> Point: ...
    def contains(self, point: Point) -> bool: ...
    def to_tuple(self) -> tuple[int, int, int, int]: ...
```

**依赖**：无（第一个任务）

---

#### T02 — 异常体系 `core/exceptions.py`

**目标**：定义 SDK 自己的异常类，让上层能 catch 特定错误。

**验收标准**：
- [ ] `src/desktop_pilot/core/exceptions.py` 存在
- [ ] 所有异常继承自 `DesktopPilotError`（基类）
- [ ] `ElementNotFoundError`：找控件找不到时抛
- [ ] `WindowNotFoundError`：找窗口找不到时抛
- [ ] `TimeoutError`：wait_for 超时时抛（注意：不要用 builtin TimeoutError，要用 `WaitTimeoutError` 避免冲突）
- [ ] `PlatformError`：平台后端调用失败时抛
- [ ] `UnsupportedOperationError`：当前平台不支持某操作时抛
- [ ] 每个异常接受 message + 可选 details 字典

**实现提示**：
```python
class DesktopPilotError(Exception): ...
class ElementNotFoundError(DesktopPilotError): ...
class WindowNotFoundError(DesktopPilotError): ...
class WaitTimeoutError(DesktopPilotError): ...  # 别叫 TimeoutError，冲突
class PlatformError(DesktopPilotError): ...
class UnsupportedOperationError(DesktopPilotError): ...
```

**依赖**：T01（无需类型，但建议先做完 T01）

---

#### T03 — 元素模型 `core/element.py`

**目标**：定义 Window / Control / Element 三种"屏幕上能看到的东西"的数据模型。

**验收标准**：
- [ ] `src/desktop_pilot/core/element.py` 存在
- [ ] `ControlType` 枚举：`BUTTON, EDIT, TEXT, LIST, CHECKBOX, COMBOBOX, MENU, MENUITEM, TAB, LINK, IMAGE, UNKNOWN`
- [ ] `Element` 基类：name, control_type, rect, enabled, visible, parent
- [ ] `Control(Element)`：额外有 value（输入框的当前内容）、children
- [ ] `Window(Control)`：额外有 hwnd（Windows 窗口句柄）、pid（进程 ID）
- [ ] 所有类有 `to_dict()` 方法（用于序列化给 LLM 看）
- [ ] `find_child(name="发送")` 方法：在子树里按名字找
- [ ] `walk()` 生成器：DFS 遍历所有后代

**实现提示**：
```python
from enum import Enum

class ControlType(Enum):
    BUTTON = "Button"
    EDIT = "Edit"
    TEXT = "Text"
    LIST = "List"
    # ... 见上

@dataclass
class Element:
    name: str
    control_type: ControlType
    rect: Rect
    enabled: bool = True
    visible: bool = True
    parent: Optional["Element"] = None
    def to_dict(self) -> dict: ...
    def find_child(self, name: str = None, control_type: ControlType = None) -> Optional["Element"]: ...
    def walk(self): ...  # yield self, then DFS children
```

**依赖**：T01（用 Rect），T02（用不到，但建议先有）

---

#### T04 — 平台抽象 `core/platform.py`

**目标**：定义 `Platform` 抽象基类，规定所有平台后端必须实现的方法签名。

**验收标准**：
- [ ] `src/desktop_pilot/core/platform.py` 存在
- [ ] `Platform` 是 `ABC`，用 `@abstractmethod` 装饰所有方法
- [ ] 必须实现的方法（签名要稳定，下游照着实现）：
  - `screenshot() -> bytes` （返回 PNG bytes）
  - `list_windows() -> list[Window]`
  - `find_window(title: str = None, title_contains: str = None, pid: int = None) -> Window`
  - `list_elements(window: Window) -> list[Element]`
  - `click(x: int, y: int) -> None`
  - `double_click(x: int, y: int) -> None`
  - `right_click(x: int, y: int) -> None`
  - `type_text(text: str) -> None`
  - `key_press(key: str) -> None`  # key 是 "enter"/"tab"/"ctrl+c" 这种
  - `scroll(direction: str, amount: int) -> None`  # direction: up/down/left/right
  - `drag(x1: int, y1: int, x2: int, y2: int) -> None`
  - `close() -> None` （清理资源）

**实现提示**：
```python
from abc import ABC, abstractmethod

class Platform(ABC):
    @abstractmethod
    def screenshot(self) -> bytes: ...
    @abstractmethod
    def list_windows(self) -> list[Window]: ...
    # ... 其他同上
```

**依赖**：T01, T03

---

#### T05 — Windows 后端 `platforms/windows.py`（**最关键的实现**）

**目标**：用 pywinauto + PyAutoGUI 实现 Windows 平台后端，是 SDK 真正能干活的部分。

**验收标准**：
- [ ] `src/desktop_pilot/platforms/windows.py` 存在
- [ ] `class WindowsPlatform(Platform)` 继承 T04 的抽象基类
- [ ] 构造函数无参数，自动初始化 pywinauto
- [ ] `screenshot()` 用 pyautogui.screenshot() 返回 PNG bytes
- [ ] `list_windows()` 枚举所有可见顶层窗口，过滤掉隐藏的，返回 Window 列表
- [ ] `find_window()` 支持精确匹配 / 子串匹配 / pid 匹配，找不到抛 WindowNotFoundError
- [ ] `list_elements(window)` 用 pywinauto 的 `window.descendants()` 拿到控件树，转成 Element
- [ ] `click(x, y)` 用 pyautogui.click，**必须先激活窗口**（避免点到别的窗口）
- [ ] `type_text(text)` 用 pyautogui.typewrite
- [ ] `key_press(key)` 把 "enter" / "ctrl+c" 转成 pyautogui 的 key 格式
- [ ] **重要**：在 click / type_text 前必须先激活目标窗口（避免焦点丢失），可参考之前踩的坑
- [ ] `close()` 不需要特殊操作（pywinauto 无显式 close）

**实现提示**：
```python
import pyautogui
import win32gui
import ctypes
import time
from pywinauto import Application, findwindows
from ..core.platform import Platform
from ..core.types import Rect, Point
from ..core.element import Window, Control, Element, ControlType
from ..core.exceptions import WindowNotFoundError, ElementNotFoundError

class WindowsPlatform(Platform):
    def __init__(self):
        self._apps = {}  # hwnd -> Application 缓存
    
    def _activate_window(self, hwnd: int):
        """把窗口拉到前台。Windows 经常拒绝 SetForegroundWindow，要用 AttachThreadInput 大法。"""
        ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        fg = ctypes.windll.user32.GetForegroundWindow()
        fg_tid = ctypes.windll.user32.GetWindowThreadProcessId(fg, 0)
        me_tid = ctypes.windll.kernel32.GetCurrentThreadId()
        ctypes.windll.user32.AttachThreadInput(fg_tid, me_tid, 1)
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        ctypes.windll.user32.SetFocus(hwnd)
        ctypes.windll.user32.AttachThreadInput(fg_tid, me_tid, 0)
        time.sleep(0.2)
    
    def screenshot(self) -> bytes:
        img = pyautogui.screenshot()
        from io import BytesIO
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    
    # ... 其他方法
```

**已知坑**（必看）：
1. `pyautogui.click` 在 Windows 上有时被 `terminal` 进程抢焦点，必须先 `_activate_window`
2. Godot / Unity 游戏**没有标准 UIA 子控件**，`EnumChildWindows` 返回空
3. `SetForegroundWindow` 经常被 Windows 拒绝，必须用 `AttachThreadInput` 三步走

**依赖**：T01, T02, T03, T04

---

#### T06 — 顶层 API `__init__.py`

**目标**：把 SDK 的公开 API 暴露到 `desktop_pilot` 顶层，让用户 `from desktop_pilot import Desktop` 就能用。

**验收标准**：
- [ ] `src/desktop_pilot/__init__.py` 重写
- [ ] 暴露 `Desktop`, `Window`, `Control`, `Element`, `ControlType`, `Rect`, `Point`
- [ ] 暴露所有异常类
- [ ] 暴露 `__version__`
- [ ] `Desktop` 类：自动检测平台（Windows/macOS/Linux），lazy 加载对应 Platform
- [ ] `Desktop` 类实现 context manager（`with Desktop() as bot:`）
- [ ] `Desktop` 把 Platform 的方法**直接代理**出去（用户不用关心 Platform 存在）

**实现提示**：
```python
import sys
from .core.types import Point, Size, Rect
from .core.element import Element, Control, Window, ControlType
from .core.exceptions import *

__version__ = "0.1.0"

class Desktop:
    def __init__(self):
        if sys.platform == "win32":
            from .platforms.windows import WindowsPlatform
            self._platform = WindowsPlatform()
        elif sys.platform == "darwin":
            from .platforms.macos import MacOSPlatform
            self._platform = MacOSPlatform()
        else:
            from .platforms.linux import LinuxPlatform
            self._platform = LinuxPlatform()
    
    def __getattr__(self, name):
        return getattr(self._platform, name)
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self._platform.close()

__all__ = ["Desktop", "Window", "Control", "Element", "ControlType", "Point", "Size", "Rect"]
```

**依赖**：T01, T02, T03, T05

---

#### T07 — 基础示例 `examples/basic_usage.py`

**目标**：5 行能跑的 demo，证明 SDK 能工作。

**验收标准**：
- [ ] `examples/basic_usage.py` 存在
- [ ] 列出当前所有可见窗口，打印前 5 个的标题
- [ ] 找到标题含 "微信" 的窗口（找不到就跳过，别 crash）
- [ ] 列出该窗口的前 10 个子控件
- [ ] 截全屏，存到 `screenshot.png`
- [ ] 在本机（Windows）能直接 `python examples/basic_usage.py` 跑通

**实现提示**：
```python
from desktop_pilot import Desktop

with Desktop() as bot:
    windows = bot.list_windows()
    print(f"Found {len(windows)} windows:")
    for w in windows[:5]:
        print(f"  - {w.name} @ {w.rect.to_tuple()}")
    
    try:
        win = bot.find_window(title_contains="微信")
        print(f"\n微信窗口: {win.name}")
        elements = bot.list_elements(window=win)
        print(f"  {len(elements)} elements")
        for e in elements[:10]:
            print(f"  - {e.control_type.value}: {e.name}")
    except Exception as e:
        print(f"微信窗口没找到，跳过: {e}")
    
    png = bot.screenshot()
    with open("screenshot.png", "wb") as f:
        f.write(png)
    print(f"\n截图保存: screenshot.png ({len(png)} bytes)")
```

**依赖**：T06

---

#### T08 — 核心单测 `tests/unit/test_core.py`

**目标**：用 mock 给 core 模块写单测，不依赖真实 Windows。

**验收标准**：
- [ ] `tests/unit/test_core.py` 存在
- [ ] 用 pytest 框架
- [ ] 至少 10 个测试，覆盖：
  - `types.py`：Point.to_tuple, Rect.center, Rect.contains
  - `exceptions.py`：每个异常类都能被 raise 和 catch
  - `element.py`：find_child / walk / to_dict
  - `platform.py`：mock Platform 子类能正常实例化
- [ ] `pytest tests/unit/test_core.py` 全绿

**实现提示**：
```python
import pytest
from desktop_pilot.core.types import Point, Rect
from desktop_pilot.core.exceptions import ElementNotFoundError

def test_point_to_tuple():
    assert Point(1, 2).to_tuple() == (1, 2)

def test_rect_center():
    r = Rect(0, 0, 100, 100)
    assert r.center == Point(50, 50)

def test_rect_contains():
    r = Rect(0, 0, 100, 100)
    assert r.contains(Point(50, 50))
    assert not r.contains(Point(200, 200))

# ... 更多
```

**依赖**：T01, T02, T03, T04

---

### P1 — Agent 友好层

#### T09 — 高级点击 `actions/click.py`

**目标**：提供 `click_button(name)` / `click_text(text)` 这种按名字找控件再点的 API，省得 agent 记坐标。

**验收标准**：
- [ ] `src/desktop_pilot/actions/click.py` 存在
- [ ] `click_button(window, name, exact=True)`：在 window 的控件树里找 name 匹配的 Button，点它的 center
- [ ] `click_text(window, text)`：找文本含 text 的任意元素，点击
- [ ] 找不到抛 ElementNotFoundError，错误信息要包含 window 标题 + 找了啥
- [ ] 多个匹配默认点第一个，可选 `index=0` 参数
- [ ] 点击前自动 `_activate_window`
- [ ] 写单测：mock Platform，验证 find_child 路径走对了

**实现提示**：
```python
from ..core.element import ControlType
from ..core.exceptions import ElementNotFoundError

def click_button(platform, window, name: str, exact: bool = True, index: int = 0):
    """按名字找按钮并点击。"""
    elements = platform.list_elements(window)
    matches = []
    for e in elements:
        e.walk()  # 遍历所有后代
        # 实际逻辑：DFS 找 button
    # ...
```

**依赖**：T05, T06

---

#### T10 — 按名字输入 `actions/type_text.py`

**目标**：`type_into(window, field, text)` 按名字找输入框再输入。

**验收标准**：
- [ ] `src/desktop_pilot/actions/type_text.py` 存在
- [ ] `type_into(window, field, text)`：找 name 含 field 的 Edit 控件，click + type_text
- [ ] 找不到抛 ElementNotFoundError
- [ ] 输入前自动清空（Ctrl+A + Delete）
- [ ] 写单测

**依赖**：T05, T06, T09（用 click_button 思路）

---

#### T11 — 等待元素 `actions/wait.py`

**目标**：`wait_for(text, timeout)` 轮询直到某元素出现。

**验收标准**：
- [ ] `src/desktop_pilot/actions/wait.py` 存在
- [ ] `wait_for(text=None, name=None, window=None, timeout=10, poll_interval=0.5)`
- [ ] 在 timeout 秒内每 poll_interval 秒检查一次
- [ ] 找到返回 Element；超时抛 WaitTimeoutError，错误信息包含等了多久 + 找了啥
- [ ] `wait_until_gone(text)` 反向
- [ ] 写单测：mock Platform，验证轮询逻辑

**实现提示**：
```python
import time
def wait_for(platform, text=None, name=None, window=None, timeout=10, poll_interval=0.5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        # 在 windows 里找
        for w in (platform.list_windows() if window is None else [window]):
            for e in platform.list_elements(window=w):
                if (text and text in (e.name or "")) or (name and name == e.name):
                    return e
        time.sleep(poll_interval)
    raise WaitTimeoutError(f"等了 {timeout}s 没找到 text={text!r} name={name!r}")
```

**依赖**：T05, T06

---

#### T12 — 批量填表 `actions/form.py`

**目标**：`fill_form(window, {"用户名": "admin", "密码": "123"})` 一次填完。

**验收标准**：
- [ ] `src/desktop_pilot/actions/form.py` 存在
- [ ] `fill_form(window, fields: dict[str, str])`
- [ ] 对每个 (字段名, 值)：找 name 含字段名的 Edit，输入值
- [ ] 任何字段找不到抛 ElementNotFoundError，已填的不回滚（让用户自己决定）
- [ ] 写单测

**依赖**：T10

---

#### T13 — OCR 兜底 `vision/ocr.py`

**目标**：UIA 拿不到文字时（游戏 canvas / 自绘控件），用 OCR 兜底。

**验收标准**：
- [ ] `src/desktop_pilot/vision/ocr.py` 存在
- [ ] `find_text(platform, text, region=None) -> list[Rect]`：截屏 + OCR + 返回所有匹配位置
- [ ] 用 pytesseract（可选依赖，没装就给友好提示）
- [ ] `region: Rect = None`：只在该区域搜，省时间
- [ ] 写单测：mock pytesseract.image_to_data

**实现提示**：
```python
def find_text(platform, text: str, region: Rect = None) -> list[Rect]:
    try:
        import pytesseract
    except ImportError:
        raise ImportError("OCR 需要 pytesseract: pip install desktop-pilot[ocr]")
    png = platform.screenshot()
    # ... OCR + 匹配
```

**依赖**：T05

---

#### T14 — 截图工具 `vision/screenshot.py`

**目标**：封装截图 + base64 + 压缩，方便传给 LLM。

**验收标准**：
- [ ] `src/desktop_pilot/vision/screenshot.py` 存在
- [ ] `screenshot_b64(platform, max_size_kb=500) -> str`：截图后压缩到不超过 max_size_kb，返回 base64
- [ ] 自动按 JPEG 质量调（80→60→40 直到达标）
- [ ] `screenshot_to_file(platform, path)`：直接存盘
- [ ] 写单测：mock 截图 bytes

**依赖**：T05

---

#### T15 — 浏览器示例 `examples/open_browser.py`

**目标**：演示完整流程——开浏览器、搜内容、点链接。

**验收标准**：
- [ ] `examples/open_browser.py` 存在
- [ ] 用 pyautogui.hotkey("ctrl") 之类开浏览器
- [ ] 等浏览器出现（wait_for 标题含 "Chrome"）
- [ ] 找地址栏（Edit 类型）输入 URL
- [ ] 按 Enter
- [ ] 注释清晰，每步 `print` 当前状态

**实现提示**：
```python
from desktop_pilot import Desktop
import pyautogui

with Desktop() as bot:
    # 1. 开浏览器
    pyautogui.hotkey("ctrl")  # 或者 win key
    # ...
```

**依赖**：T11 (wait_for)

---

### P2 — 框架集成

#### T16 — LangChain 适配 `integrations/langchain.py`

**目标**：把核心 API 包成 LangChain Tool，给 agent 用。

**验收标准**：
- [ ] `src/desktop_pilot/integrations/langchain.py` 存在
- [ ] 提供 `get_tools() -> list[BaseTool]`
- [ ] 每个 Tool 有清晰的 name + description（LLM 靠这个决定调不调）
- [ ] Tools 至少包含：screenshot, list_windows, click_button, type_into, wait_for
- [ ] 可选依赖 `langchain-core`，没装就抛 ImportError 提示装
- [ ] 写单测

**实现提示**：
```python
def get_tools():
    try:
        from langchain_core.tools import BaseTool
    except ImportError:
        raise ImportError("pip install desktop-pilot[langchain]")
    
    class ScreenshotTool(BaseTool):
        name = "desktop_screenshot"
        description = "截取当前屏幕，返回 base64 PNG"
        def _run(self): ...
    
    return [ScreenshotTool(), ...]
```

**依赖**：T06

---

#### T17 — Function Calling schema `integrations/function_call.py`

**目标**：导出 OpenAI/Anthropic function calling 的 JSON schema。

**验收标准**：
- [ ] `src/desktop_pilot/integrations/function_call.py` 存在
- [ ] `get_tools_schema() -> list[dict]`：返回 OpenAI tools 格式
- [ ] 至少 5 个函数：screenshot, list_windows, click, type_text, key_press
- [ ] 每个函数有清晰的 description + parameters (JSON schema)
- [ ] 写单测：验证 schema 是合法 JSON

**实现提示**：
```python
def get_tools_schema():
    return [
        {
            "type": "function",
            "function": {
                "name": "desktop_screenshot",
                "description": "截取当前屏幕...",
                "parameters": {"type": "object", "properties": {}, "required": []}
            }
        },
        # ...
    ]
```

**依赖**：T06

---

#### T18 — LangChain agent 示例 `examples/langchain_agent.py`

**目标**：展示真实 agent 怎么用这 SDK。

**验收标准**：
- [ ] `examples/langchain_agent.py` 存在
- [ ] 接 OpenAI function calling
- [ ] 给 agent 一个任务："打开浏览器搜 Python 教程"
- [ ] agent 自己决定调哪些 tools，完成任务
- [ ] 注释清晰，可直接 `OPENAI_API_KEY=xxx python examples/langchain_agent.py` 跑

**依赖**：T16, T17

---

### P3 — 跨平台 stub

#### T19 — macOS stub `platforms/macos.py`

**目标**：占位实现，抛 NotImplementedError，但接口对齐。

**验收标准**：
- [ ] `src/desktop_pilot/platforms/macos.py` 存在
- [ ] `class MacOSPlatform(Platform)` 实现所有抽象方法
- [ ] 每个方法抛 UnsupportedOperationError，错误信息提示"macOS 暂未实现，欢迎贡献"
- [ ] 写单测：每个方法都抛异常

**依赖**：T04

---

#### T20 — Linux stub `platforms/linux.py`

**目标**：同上，Linux 占位。

**验收标准**：
- [ ] `src/desktop_pilot/platforms/linux.py` 存在
- [ ] `class LinuxPlatform(Platform)` 所有方法抛 UnsupportedOperationError
- [ ] 写单测

**依赖**：T04

---

### P4 — 收尾

#### T21 — 完整单测

**目标**：所有模块都有单测，`pytest tests/unit` 全绿。

**验收标准**：
- [ ] tests/unit/ 下每个模块都有对应 test_xxx.py
- [ ] 覆盖率 ≥ 80%
- [ ] `pytest tests/unit -v` 全绿

**依赖**：所有 P0-P3 任务

---

#### T22 — 真实环境验证 basic_usage

**目标**：在本机跑通 T07 的例子。

**验收标准**：
- [ ] `python examples/basic_usage.py` 在 Windows 上跑通
- [ ] 至少列出 5 个真实窗口
- [ ] 截屏文件能正常打开

**依赖**：T07

---

#### T23 — 真实环境验证 open_browser

**目标**：跑通浏览器自动化示例。

**验收标准**：
- [ ] `python examples/open_browser.py` 在 Windows + Chrome 上跑通
- [ ] 浏览器被打开，地址栏被填入

**依赖**：T15

---

#### T24 — 完善文档

**目标**：让 README + 文档站完整。

**验收标准**：
- [ ] README 加 install badge / pypi 链接
- [ ] 写 docs/getting_started.md（10 分钟教程）
- [ ] 写 docs/api_reference.md（每个 API 一段）
- [ ] 写 CONTRIBUTING.md

**依赖**：所有其他任务

---

## 验收检查清单

- [x] `python examples/basic_usage.py` 在 Windows 上跑通（列出窗口 + 读微信控件树 + 截图，实测通过）
- [x] `python examples/open_browser.py` 跑通（Win+R 启动浏览器 → Ctrl+L 聚焦地址栏 → 输入 URL → 回车 → 截图 → 关标签，实测通过）
- [x] `pytest tests/unit -v` 全绿（106 个单测，~89% 覆盖率）
- [x] `pytest tests/integration -m integration` 全绿（3 个真实 Windows：枚举窗口 / 截图 / 读控件树）
- [x] 高 DPI 下坐标对齐（125% 缩放机器实测：UIA 控件中心 → 真实光标落点 0 像素偏差）
- [x] Hermes MCP 接入（`hermes mcp test desktop-pilot` → 22 工具，截图返回物理分辨率图像）
- [ ] `pip install -e ".[all]"` 全量安装（构建已验证；OCR 运行时需另装 tesseract 系统二进制）
- [ ] LangChain agent 示例跑通（`get_tools` 单测已覆盖；`langchain_agent.py` 需 OpenAI API key，按需运行）

## 安装

```bash
cd D:\codeshit\DesktopPilot
pip install -e ".[all]"
```

依赖见 `pyproject.toml`：
- 必装：pyautogui, Pillow, pywinauto
- 可选：pytesseract（OCR）, opencv-python（视觉）, langchain-core（集成）

---

## 接入其他 agent

### OpenAI Function Calling
```python
from desktop_pilot.integrations.function_call import get_tools_schema
# get_tools_schema() -> list[dict]，直接塞给 OpenAI API
```

### LangChain
```python
from desktop_pilot.integrations.langchain import get_tools
tools = get_tools()
# tools -> list[BaseTool]，给 LangChain agent 用
```

---

## 路线图

**v0.1** ✅ MVP：P0 + P1 完成，可 pip install 使用
**v0.2** ✅ 统一工具注册表 + MCP server + 完整鼠标 API（左/右/中键、滚轮、按下/松开、拖拽）
**v0.2.1** ✅ Hermes 实战修复：MCP 1.x 兼容 + 高 DPI 点击偏移 + 构建修复
**v0.3** 🔜 P3：macOS / Linux 至少能跑基础 API（当前为 stub）
**v1.0** 目标：完整测试覆盖 + 文档站 + 性能 benchmark + PyPI 正式发布，API 锁定稳定

---

## 跟现有方案对比

| 方案 | 元素级 API | 跨平台 | 开源 | Agent 友好 |
|---|---|---|---|---|
| PyAutoGUI | ❌ | ✅ | ✅ | ❌ 坐标 |
| Selenium | ✅ | ✅ | ✅ | ⚠️ 仅浏览器 |
| Computer Use | ❌ | ✅ | ❌ API 收费 | ⚠️ 截图驱动 |
| **DesktopPilot** | ✅ | 🔜 | ✅ | ✅ |
