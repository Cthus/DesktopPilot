"""错误体系的增强测试。

覆盖：
- DesktopPilotError.with_details / traceback_text；
- 注册表分发边界：预期错误只带业务上下文、意外错误带完整 traceback、
  调试模式两者都带、arguments 上下文总是带；
- Windows 后端 _contextualize 装饰器：外来异常 → PlatformError+环境快照，
  DesktopPilotError 原地附环境快照；
- _context_snapshot 在缺 win32 属性时绝不抛错。
"""
from __future__ import annotations

import types

import pytest

from desktop_pilot.core.exceptions import (
    DesktopPilotError,
    ElementNotFoundError,
    PlatformError,
)
from desktop_pilot.tools import ToolRegistry

from .conftest import FakePlatform, attach_roots, make_button, make_window


# --------------------------------------------------------------------------- #
# 异常基类增强
# --------------------------------------------------------------------------- #
def test_with_details_chains_and_skips_none():
    err = ElementNotFoundError("boom").with_details(a=1, b=None, c="x")
    assert err.details == {"a": 1, "c": "x"}
    assert isinstance(err, ElementNotFoundError)


def test_traceback_text_contains_frame():
    try:
        raise ElementNotFoundError("找不到")
    except ElementNotFoundError as e2:
        text = e2.traceback_text
    assert "test_traceback_text_contains_frame" in text
    assert "ElementNotFoundError" in text


# --------------------------------------------------------------------------- #
# 注册表分发边界
# --------------------------------------------------------------------------- #
def _registry_calling(handler):
    from desktop_pilot import Desktop
    from desktop_pilot.tools.spec import ToolSpec

    bot = Desktop(platform=FakePlatform())
    registry = ToolRegistry(bot)
    # 手动塞一个会抛异常的 spec
    registry._tools["t_fail"] = ToolSpec(
        name="t_fail",
        description="失败测试工具",
        parameters={"type": "object", "properties": {}},
        handler=handler,
    )
    return registry


def test_expected_error_has_details_and_arguments_but_not_traceback():
    def handler(_args):
        raise ElementNotFoundError(
            "找不到按钮",
            details={"window": "设置", "name": "确定", "nearby": ["取消", "应用"]},
        )

    registry = _registry_calling(handler)
    r = registry.call("t_fail", {"x": 1, "y": 2})
    assert r.ok is False
    assert r.error["type"] == "ElementNotFoundError"
    assert r.error["details"]["window"] == "设置"
    # arguments 上下文总带（复现用）
    assert r.error["context"]["arguments"] == {"x": 1, "y": 2}
    # 预期错误默认不带 traceback（避免噪音，靠 details 就够）
    assert "traceback" not in r.error


def test_unexpected_error_includes_traceback_and_is_internal():
    def handler(_args):
        raise RuntimeError("内部爆炸")

    registry = _registry_calling(handler)
    r = registry.call("t_fail", {})
    assert r.ok is False
    assert r.error["type"] == "InternalError"
    assert "traceback" in r.error
    assert "RuntimeError" in r.error["traceback"]
    assert "内部爆炸" in r.error["traceback"]
    assert r.error["context"]["arguments"] == {}


def test_debug_mode_adds_traceback_to_expected_error(monkeypatch):
    def handler(_args):
        raise ElementNotFoundError("找不到按钮")

    registry = _registry_calling(handler)
    # 模拟 DESKTOP_PILOT_DEBUG=1
    monkeypatch.setattr("desktop_pilot.tools.registry.debug_enabled", lambda: True)
    r = registry.call("t_fail", {})
    assert "traceback" in r.error
    assert "ElementNotFoundError" in r.error["traceback"]


def test_unknown_tool_still_leaves_no_traceback():
    registry = _registry_calling(lambda _a: None)
    r = registry.call("desktop_nope", {})
    assert r.error["type"] == "UnknownTool"
    assert "traceback" not in r.error


# --------------------------------------------------------------------------- #
# Windows 后端 _contextualize 装饰器
# --------------------------------------------------------------------------- #
@pytest.fixture
def contextualized_dummy():
    from desktop_pilot.platforms.windows import _contextualize

    class Dummy:
        def __init__(self):
            self._user32 = types.SimpleNamespace()

        def _context_snapshot(self):
            return {"screen_size": [1920, 1080], "dpi_scale_pct": 125}

        @_contextualize
        def boom(self):
            raise RuntimeError("kaboom")

        @_contextualize
        def miss(self):
            raise ElementNotFoundError("没有")

        @_contextualize
        def bad_arg(self):
            raise ValueError("参数不对")

        @_contextualize
        def fine(self):
            return "ok"

    return Dummy()


def test_contextualize_wraps_foreign_exception_with_env(contextualized_dummy):
    with pytest.raises(PlatformError) as ei:
        contextualized_dummy.boom()
    assert "RuntimeError" in str(ei.value)
    assert ei.value.details["env"]["screen_size"] == [1920, 1080]
    # 与原始异常链式相连，PyCharm/日志能看到 cause
    assert isinstance(ei.value.__cause__, RuntimeError)


def test_contextualize_attaches_env_to_desktop_error(contextualized_dummy):
    with pytest.raises(ElementNotFoundError) as ei:
        contextualized_dummy.miss()
    assert ei.value.details["env"]["dpi_scale_pct"] == 125


def test_contextualize_preserves_validation_errors(contextualized_dummy):
    with pytest.raises(ValueError):
        contextualized_dummy.bad_arg()


def test_contextualize_passes_success_through(contextualized_dummy):
    assert contextualized_dummy.fine() == "ok"


def test_context_snapshot_defensive_with_empty_user32():
    from desktop_pilot.platforms.windows import WindowsPlatform

    p = WindowsPlatform.__new__(WindowsPlatform)  # type: ignore[call-arg]
    p._user32 = types.SimpleNamespace()  # 啥都没有
    snap = p._context_snapshot()  # 必须不抛
    assert isinstance(snap, dict)
    assert "screen_size" not in snap  # 探测失败就跳过，绝不炸