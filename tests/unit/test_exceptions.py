"""T02 异常体系单测。"""
from __future__ import annotations

import pytest

from desktop_pilot.core import exceptions as exc
from desktop_pilot.core.exceptions import (
    DesktopPilotError,
    ElementNotFoundError,
    PlatformError,
    UnsupportedOperationError,
    WaitTimeoutError,
    WindowNotFoundError,
)

ALL_ERRORS = [
    ElementNotFoundError,
    WindowNotFoundError,
    WaitTimeoutError,
    PlatformError,
    UnsupportedOperationError,
]


@pytest.mark.parametrize("cls", ALL_ERRORS)
def test_each_error_inherits_base(cls):
    assert issubclass(cls, DesktopPilotError)


@pytest.mark.parametrize("cls", ALL_ERRORS)
def test_error_message_and_details(cls):
    err = cls("boom", details={"k": "v"})
    assert err.message == "boom"
    assert err.details == {"k": "v"}
    assert "boom" in str(err)


def test_can_raise_and_catch_specific():
    with pytest.raises(ElementNotFoundError):
        raise ElementNotFoundError("no button")


def test_base_catches_all():
    with pytest.raises(DesktopPilotError):
        raise WaitTimeoutError("timed out")


def test_does_not_shadow_builtin_timeout():
    # 我们的超时异常不叫 TimeoutError，避免与内置冲突。
    assert not hasattr(exc, "TimeoutError")
    assert WaitTimeoutError is not TimeoutError  # builtin
