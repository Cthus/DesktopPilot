"""T03 元素模型单测。"""
from __future__ import annotations

from desktop_pilot.core.element import Control, ControlType, Element, Window
from desktop_pilot.core.types import Point, Rect


def _tree():
    """构造一个三层控件树。"""
    root = Element("对话框", ControlType.WINDOW, Rect(0, 0, 400, 300))
    ok = Element("确定", ControlType.BUTTON, Rect(0, 200, 80, 240))
    cancel = Element("取消", ControlType.BUTTON, Rect(90, 200, 170, 240))
    user_edit = Element("用户名", ControlType.EDIT, Rect(0, 0, 200, 30), value="admin")
    nested = Element("分组", ControlType.PANE, Rect(0, 0, 400, 200))
    inner_btn = Element("发送", ControlType.BUTTON, Rect(0, 0, 50, 30))

    root.children = [user_edit, nested, ok, cancel]
    nested.children = [inner_btn]
    for c in root.children:
        c.parent = root
    inner_btn.parent = nested
    return root, ok, cancel, user_edit, nested, inner_btn


def test_control_type_values():
    assert ControlType.BUTTON.value == "Button"
    assert ControlType.EDIT.value == "Edit"
    assert ControlType.UNKNOWN.value == "Unknown"


def test_find_child_exact():
    root, ok, *_ = _tree()
    found = root.find_child(name="确定")
    assert found is ok


def test_find_child_substring():
    root, *_, inner_btn = _tree()
    found = root.find_child(name="送", exact=False)
    assert found is inner_btn


def test_find_child_by_type():
    root, *_ = _tree()
    found = root.find_child(control_type=ControlType.EDIT)
    assert found is not None and found.control_type == ControlType.EDIT
    assert found.value == "admin"


def test_find_child_returns_none_when_absent():
    root, *_ = _tree()
    assert root.find_child(name="不存在的按钮") is None


def test_walk_dfs_visits_all():
    root, *_ = _tree()
    names = [e.name for e in root.walk()]
    # 自身 + 4 个一级孩子 + 1 个孙子 = 6
    assert names == ["对话框", "用户名", "分组", "发送", "确定", "取消"]


def test_to_dict_serializable():
    root, *_ = _tree()
    d = root.to_dict()
    assert d["name"] == "对话框"
    assert d["control_type"] == "Window"
    assert d["rect"] == (0, 0, 400, 300)
    # 子树递归序列化
    assert isinstance(d["children"], list)
    assert len(d["children"]) == 4
    assert "parent" not in d  # 不能序列化 parent（会成环）


def test_window_has_hwnd_pid():
    w = Window(
        name="win",
        control_type=ControlType.WINDOW,
        rect=Rect(0, 0, 10, 10),
        hwnd=123,
        pid=456,
    )
    d = w.to_dict()
    assert d["hwnd"] == 123
    assert d["pid"] == 456
    assert isinstance(w, Control)
    assert isinstance(w, Element)


def test_contains_point():
    el = Element("x", ControlType.BUTTON, Rect(10, 10, 50, 50))
    assert el.contains_point(Point(30, 30))
    assert not el.contains_point(Point(0, 0))
