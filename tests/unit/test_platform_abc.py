"""T04 平台抽象 + T19/T20 stub 单测。"""
from __future__ import annotations

import pytest

from desktop_pilot.core.exceptions import UnsupportedOperationError
from desktop_pilot.core.platform import Platform
from desktop_pilot.platforms.linux import LinuxPlatform
from desktop_pilot.platforms.macos import MacOSPlatform


def test_cannot_instantiate_abc():
    with pytest.raises(TypeError):
        Platform()  # type: ignore[abstract]


def test_mock_subclass_instantiates(fake_platform):
    # conftest 里的 FakePlatform 继承 Platform，应当能实例化并代理调用。
    assert isinstance(fake_platform, Platform)
    fake_platform.click(1, 2)
    assert fake_platform.clicks == [(1, 2)]


@pytest.mark.parametrize("cls", [MacOSPlatform, LinuxPlatform])
def test_stubs_raise_unsupported(cls):
    p = cls()
    with pytest.raises(UnsupportedOperationError):
        p.screenshot()
    with pytest.raises(UnsupportedOperationError):
        p.list_windows()
    with pytest.raises(UnsupportedOperationError):
        p.find_window(title="x")
    with pytest.raises(UnsupportedOperationError):
        p.click(0, 0)
    with pytest.raises(UnsupportedOperationError):
        p.double_click(0, 0)
    with pytest.raises(UnsupportedOperationError):
        p.right_click(0, 0)
    with pytest.raises(UnsupportedOperationError):
        p.type_text("x")
    with pytest.raises(UnsupportedOperationError):
        p.key_press("enter")
    with pytest.raises(UnsupportedOperationError):
        p.scroll("up")
    with pytest.raises(UnsupportedOperationError):
        p.drag(0, 0, 1, 1)


@pytest.mark.parametrize("cls", [MacOSPlatform, LinuxPlatform])
def test_stub_close_is_noop(cls):
    # close 不抛异常，保证 with Desktop() 在未实现平台也能干净退出。
    p = cls()
    assert p.close() is None
