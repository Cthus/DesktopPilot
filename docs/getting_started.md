# 快速开始（10 分钟）

本教程带你在 Windows 上从零跑起 DesktopPilot。

## 1. 安装

```bash
cd D:\codeshit\DesktopPilot
pip install -e ".[all]"
```

`[all]` 会顺带装上 OCR（pytesseract）、视觉（opencv）、LangChain 集成所需的依赖。
Windows 还会自动安装 `pywinauto`、`pywin32`、`pyautogui`。

> 想用 OCR 还需要单独安装 Tesseract 引擎本体：
> <https://github.com/UB-Mannheim/tesseract/wiki>，安装时勾选中文语言包。

验证安装：

```bash
python -c "from desktop_pilot import Desktop; print(Desktop())"
# -> <Desktop platform='win32'>
```

## 2. 看一眼当前屏幕

```python
from desktop_pilot import Desktop

with Desktop() as bot:
    windows = bot.list_windows()
    print(f"共有 {len(windows)} 个可见窗口：")
    for w in windows[:5]:
        print(f"  - {w.name}  pid={w.pid}  rect={w.rect.to_tuple()}")

    png = bot.screenshot()
    open("screenshot.png", "wb").write(png)
```

`with Desktop() as bot:` 保证退出时释放后端资源。

## 3. 找窗口、读控件树

```python
with Desktop() as bot:
    win = bot.find_window(title_contains="微信")   # 子串匹配
    # 也支持精确标题 title=... 或进程 pid=...

    roots = bot.list_elements(window=win)          # 拿到控件树根
    for el in roots[0].walk():                     # DFS 遍历所有后代
        print(el.control_type.value, el.name, el.rect.center.to_tuple())
```

你会看到类似：

```
Window 微信 (420, 602)
Pane Weixin (775, 955)
Edit 输入 (500, 900)
Button 发送 (720, 900)
```

## 4. 按语义操作（agent 最常用）

不用记坐标，按名字点按钮：

```python
with Desktop() as bot:
    win = bot.find_window(title_contains="微信")
    bot.click_button(window=win, name="发送")             # 名字完全匹配
    bot.click_button(window=win, name="发送", exact=False)  # 子串也可
```

按标签填输入框（会先点击聚焦、Ctrl+A 清空再输入）：

```python
    bot.type_into(window=win, field="输入框", text="你好")
```

批量填表：

```python
    bot.fill_form(win, {"用户名": "admin", "密码": "123456"})
```

等元素出现（轮询，默认 10s 超时）：

```python
    el = bot.wait_for(text="加载完成", timeout=15)
    bot.wait_until_gone(text="正在处理...")
```

## 5. 基础输入（坐标 / 键盘）

```python
    bot.click(500, 300)
    bot.double_click(500, 300)
    bot.right_click(500, 300)
    bot.drag(100, 100, 300, 300)
    bot.type_text("hello world")
    bot.key_press("enter")
    bot.key_press("ctrl+c")        # 组合键用 '+' 连接
    bot.scroll("down", amount=5)
```

## 6. 把画面给 LLM 看

```python
    b64 = bot.screenshot_b64(max_size_kb=500)   # 自动压成 JPEG base64
    # 直接塞进 OpenAI / Anthropic 的多模态 image_url
```

## 7. 接进 agent

- **Function Calling**：`desktop_pilot.integrations.function_call.get_tools_schema()`
  返回 OpenAI/Anthropic 兼容的 JSON schema，可直接给 `tools=`。
- **LangChain**：`desktop_pilot.integrations.langchain.get_tools(bot)`
  返回 `list[BaseTool]`，喂给 LangChain agent。

完整示例见 [`examples/`](../examples/)。

## 已知限制

- Godot / Unity / 部分自绘 UI（含部分新版微信）没有标准 UIA 子控件，
  `list_elements` 只能拿到极少节点。此时用 `screenshot_b64` + 多模态模型，
  或用 `vision.ocr.find_text` 做 OCR 定位。
- macOS / Linux 后端目前是占位实现，所有方法抛 `UnsupportedOperationError`。
- 坐标点击前会自动激活目标窗口，避免点到别的进程。
