"""T10 按名字输入 + T12 批量填表单测。"""
from __future__ import annotations

import pytest

from desktop_pilot.actions.form import fill_form
from desktop_pilot.actions.type_text import type_into
from desktop_pilot.core.exceptions import ElementNotFoundError
from desktop_pilot.core.types import Rect

from .conftest import (
    FakePlatform,
    attach_roots,
    make_edit,
    make_window,
)


def test_type_into_clicks_clears_and_types():
    w = make_window()
    edit = make_edit("用户名输入框", Rect(0, 0, 200, 30))
    attach_roots(w, [edit])
    fake = FakePlatform(windows=[w])

    type_into(fake, w, field="用户名", text="alice")
    assert fake.clicks == [(100, 15)]
    assert "ctrl+a" in fake.keys
    assert "delete" in fake.keys
    assert fake.typed == ["alice"]


def test_type_into_without_clear():
    w = make_window()
    edit = make_edit("搜索框", Rect(0, 0, 100, 20))
    attach_roots(w, [edit])
    fake = FakePlatform(windows=[w])

    type_into(fake, w, field="搜索", text="py", clear=False)
    assert "ctrl+a" not in fake.keys
    assert fake.typed == ["py"]


def test_type_into_missing_edit():
    w = make_window()
    attach_roots(w, [])
    fake = FakePlatform(windows=[w])
    with pytest.raises(ElementNotFoundError):
        type_into(fake, w, field="不存在", text="x")


def test_fill_form_multiple_fields():
    w = make_window()
    user = make_edit("用户名", Rect(0, 0, 200, 30))
    pwd = make_edit("密码", Rect(0, 40, 200, 70))
    attach_roots(w, [user, pwd])
    fake = FakePlatform(windows=[w])

    result = fill_form(fake, w, {"用户名": "admin", "密码": "secret"})
    assert set(result.keys()) == {"用户名", "密码"}
    assert fake.typed == ["admin", "secret"]
    # 每个字段一次点击
    assert len(fake.clicks) == 2


def test_fill_form_partial_failure_no_rollback():
    w = make_window()
    user = make_edit("用户名", Rect(0, 0, 200, 30))
    attach_roots(w, [user])
    fake = FakePlatform(windows=[w])

    with pytest.raises(ElementNotFoundError):
        fill_form(fake, w, {"用户名": "admin", "密码": "x"})
    # 用户名字段已填，未回滚
    assert fake.typed == ["admin"]
