"""T01 基础类型单测。"""
from __future__ import annotations

import pytest

from desktop_pilot.core.types import Point, Rect, Size


def test_point_to_tuple():
    assert Point(1, 2).to_tuple() == (1, 2)


def test_size_to_tuple():
    assert Size(100, 200).to_tuple() == (100, 200)


def test_rect_center():
    r = Rect(0, 0, 100, 100)
    assert r.center == Point(50, 50)
    assert r.size.to_tuple() == (100, 100)


def test_rect_contains():
    r = Rect(0, 0, 100, 100)
    assert r.contains(Point(50, 50)) is True
    assert r.contains(Point(0, 0)) is True  # 边界
    assert r.contains(Point(100, 100)) is True
    assert r.contains(Point(200, 200)) is False
    assert r.contains(Point(-1, 50)) is False


def test_rect_immutable():
    p = Point(1, 2)
    with pytest.raises(Exception):
        p.x = 5  # type: ignore[misc]
