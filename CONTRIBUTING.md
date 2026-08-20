# 贡献指南

感谢你有兴趣改进 DesktopPilot！

## 开发环境

```bash
git clone <your-fork>
cd DesktopPilot
pip install -e ".[dev,all]"
```

这会以可编辑模式安装包，并装上 pytest、pytest-cov、pytest-mock、black、ruff、mypy。

## 项目结构

```
src/desktop_pilot/
├── core/         # 平台无关抽象：类型、异常、元素模型、Platform ABC
├── platforms/    # 平台后端：windows（真实实现）、macos/linux（占位）
├── actions/      # 高层语义动作：click / type / wait / form
├── vision/       # 截图与 OCR 兜底
└── integrations/ # LangChain / OpenAI Function Calling 适配
tests/unit/       # mock 单测，不依赖真实 GUI
tests/integration/# 标记 @pytest.mark.integration，需要真实 Windows 桌面
examples/         # 可直接运行的示例
```

架构核心是依赖倒置：`actions/` 只依赖 `core.platform.Platform` 抽象，
因此所有高层逻辑都能用 `FakePlatform` 做单测，无需真实桌面。

## 跑测试

```bash
# 全部单测
pytest tests/unit -v

# 覆盖率（目标 ≥ 80%）
pytest tests/unit --cov=desktop_pilot --cov-report=term-missing

# 真实 Windows 集成测试（会实际操作桌面，运行前保存好工作）
pytest tests/integration -m integration
```

## 代码风格

- 行宽 100（`black` / `ruff` 已配置）。
- 提交前：
  ```bash
  black src tests
  ruff check src tests
  mypy src
  ```
- 公共 API 要有类型注解和 docstring。
- 面向 LLM 的描述（Tool description、异常信息）用中文写清楚，这是 agent 决策的依据。

## 添加新的语义动作

1. 在 `src/desktop_pilot/actions/` 新建模块，函数第一个参数为 `platform: Platform`。
2. 找不到元素抛 `ElementNotFoundError`，错误信息带上窗口标题和找了什么。
3. 在 `Desktop` 类（`__init__.py`）加一个薄方法代理它。
4. 在 `tests/unit/` 用 `FakePlatform` 写单测。
5. 如适合 agent 调用，在 `integrations/function_call.py` 和
   `integrations/langchain.py` 各加一个工具。

## 实现 macOS / Linux 后端

- 继承 `core.platform.Platform`，实现所有抽象方法。
- macOS 建议基于 AXIsProtocol（pyobjc `ApplicationServices`）。
- Linux 建议基于 AT-SPI2（pyatspi）+ python-xlib / pynput。
- 参考 `platforms/macos.py` 的接口契约；目前它们抛 `UnsupportedOperationError`。

## 已知坑

- Windows 上 `SetForegroundWindow` 经常被拒，必须用 `AttachThreadInput`
  把当前线程 attach 到前台线程后再设置（见 `windows.py::_activate_window`）。
- Godot / Unity / 部分自绘 UI 没有标准 UIA 子控件，`list_elements` 会很稀疏，
  这类应用要走 `vision/` 的截图 / OCR 路径。
- 不要把超时异常命名为 `TimeoutError`，会和内置异常冲突——用 `WaitTimeoutError`。

## 提 PR

- 一个 PR 聚焦一件事，标题说清"做了什么、为什么"。
- 新功能带测试；修 bug 先加一个能复现的测试。
- 确认 `pytest tests/unit` 全绿再请求 review。
