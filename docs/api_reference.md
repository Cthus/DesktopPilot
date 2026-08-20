# API 参考

## 顶层入口

### `Desktop(platform=None)`

桌面自动化入口。自动检测平台（Windows/macOS/Linux）并加载对应后端。
也可注入自定义 `platform`（用于测试 mock）。

```python
from desktop_pilot import Desktop

with Desktop() as bot:
    bot.screenshot()
```

`Desktop` 是 context manager，`__exit__` 会调用 `platform.close()`。

### 感知

| 方法 | 说明 |
|---|---|
| `screenshot() -> bytes` | 截全屏，返回 PNG 字节 |
| `screenshot_b64(max_size_kb=500) -> str` | 截图并返回压缩后的 base64 JPEG |
| `screenshot_to_file(path) -> str` | 截图直接存盘 |
| `list_windows() -> list[Window]` | 枚举所有可见顶层窗口 |
| `find_window(title=None, title_contains=None, pid=None) -> Window` | 查找窗口，找不到抛 `WindowNotFoundError` |
| `list_elements(window) -> list[Element]` | 取窗口控件树根（后代用 `.walk()`） |

### 基础输入

| 方法 | 说明 |
|---|---|
| `click(x, y)` / `double_click(x, y)` / `right_click(x, y)` | 坐标点击 |
| `drag(x1, y1, x2, y2)` | 鼠标拖拽 |
| `type_text(text)` | 当前焦点输入文本 |
| `key_press(key)` | 按键/组合键（`"enter"`、`"ctrl+c"`、`"alt+f4"`） |
| `scroll(direction, amount=3)` | 滚动，direction 为 up/down/left/right |

### 高层语义动作

| 方法 | 说明 |
|---|---|
| `click_button(window, name, exact=True, index=0) -> Element` | 按名字找按钮并点其中心 |
| `click_text(window, text, index=0) -> Element` | 点名字含 text 的任意元素 |
| `type_into(window, field, text, clear=True) -> Element` | 按标签找输入框，填入文本 |
| `fill_form(window, fields: dict[str,str], clear=True)` | 批量填表 |
| `wait_for(text=None, name=None, window=None, timeout=10, poll_interval=0.5) -> Element` | 等元素出现 |
| `wait_until_gone(...)` | 等元素消失 |

### 视觉 / OCR

| 方法 | 说明 |
|---|---|
| `find_text(text, region=None) -> list[Rect]` | OCR 定位屏幕文字（需 `[ocr]`） |

---

## 数据模型

### `Point(x, y)`、`Size(width, height)`、`Rect(left, top, right, bottom)`

均为 `@dataclass(frozen=True)`，不可变。

```python
r = Rect(0, 0, 100, 100)
r.center          # -> Point(50, 50)
r.contains(Point(50, 50))   # True
r.to_tuple()      # (0, 0, 100, 100)
```

### `Element` / `Control` / `Window`

```python
class Element:
    name: str
    control_type: ControlType
    rect: Rect
    enabled: bool
    visible: bool
    value: str | None      # 输入框当前内容等
    children: list[Element]
    parent: Element | None

    def to_dict() -> dict           # 序列化成 LLM 友好的 dict（不含 parent 环）
    def find_child(name=None, control_type=None, exact=True) -> Element | None
    def walk() -> Iterator[Element]  # DFS 自身+所有后代
```

`Control(Element)` 是普通控件；`Window(Control)` 额外带 `hwnd`、`pid`。

### `ControlType`

枚举值：`BUTTON, EDIT, TEXT, LIST, LISTITEM, CHECKBOX, COMBOBOX, MENU, MENUITEM,
TAB, TABITEM, LINK, IMAGE, RADIOBUTTON, PROGRESSBAR, SLIDER, TREE, TREEITEM,
WINDOW, PANE, CUSTOM, UNKNOWN`。

---

## 异常

全部继承自 `DesktopPilotError`，每个异常接受 `message` 与可选 `details: dict`：

| 异常 | 触发场景 |
|---|---|
| `ElementNotFoundError` | 找不到控件 |
| `WindowNotFoundError` | 找不到窗口 |
| `WaitTimeoutError` | wait_for / wait_until_gone 超时（**非**内置 TimeoutError） |
| `PlatformError` | 平台后端调用失败 |
| `UnsupportedOperationError` | 当前平台不支持（macOS/Linux stub） |

---

## 自定义平台后端

继承 `desktop_pilot.core.platform.Platform`，实现所有 `@abstractmethod`，
然后 `Desktop(platform=MyPlatform())` 注入即可。这也是单元测试 mock 的入口。

```python
from desktop_pilot.core.platform import Platform

class MyBackend(Platform):
    def screenshot(self) -> bytes: ...
    # 实现其余抽象方法...
```

---

## 集成层

### Function Calling

```python
from desktop_pilot.integrations.function_call import get_tools_schema
tools = get_tools_schema()   # list[dict]，直接给 OpenAI / Anthropic tools 参数
```

### LangChain

```python
from desktop_pilot import Desktop
from desktop_pilot.integrations.langchain import get_tools

with Desktop() as bot:
    tools = get_tools(bot)   # list[BaseTool]
```

需要 `pip install 'desktop-pilot[langchain]'`。
