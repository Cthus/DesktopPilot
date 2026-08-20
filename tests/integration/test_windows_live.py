"""真实 Windows 桌面集成测试（T22/T23）。

这些测试会实际枚举窗口、截图，默认不运行，需要显式标记：

    pytest tests/integration -m integration

它们不主动点击/输入（避免干扰用户工作），只验证只读能力在真实环境可用。
"""
from __future__ import annotations

import sys

import pytest

# 非 Windows 环境直接跳过整个模块；且默认不运行（需 -m integration）。
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not sys.platform.startswith("win"),
        reason="仅在 Windows 上运行",
    ),
]


def test_list_windows_returns_real_windows():
    from desktop_pilot import Desktop

    with Desktop() as bot:
        windows = bot.list_windows()
    assert isinstance(windows, list)
    # 正常运行的 Windows 至少有几个可见窗口。
    assert len(windows) >= 1
    for w in windows:
        assert w.name
        assert w.hwnd


def test_screenshot_produces_valid_png(tmp_path):
    from desktop_pilot import Desktop

    with Desktop() as bot:
        data = bot.screenshot()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    out = tmp_path / "shot.png"
    out.write_bytes(data)
    assert out.stat().st_size > 0


def test_list_elements_does_not_crash():
    """对每个可见窗口尝试读控件树；某些自绘应用可能返回稀疏树，但不应抛异常。"""
    from desktop_pilot.core.exceptions import PlatformError, WindowNotFoundError

    from desktop_pilot import Desktop

    with Desktop() as bot:
        for w in bot.list_windows()[:5]:
            try:
                roots = bot.list_elements(window=w)
            except (PlatformError, WindowNotFoundError):
                continue
            assert isinstance(roots, list)
