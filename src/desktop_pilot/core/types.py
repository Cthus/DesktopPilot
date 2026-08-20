"""基础几何类型。

所有几何计算的基石：Point / Size / Rect，全部不可变。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Point:
    """屏幕上的一个点。"""

    x: int
    y: int

    def to_tuple(self) -> tuple[int, int]:
        return (self.x, self.y)


@dataclass(frozen=True)
class Size:
    """矩形尺寸。"""

    width: int
    height: int

    def to_tuple(self) -> tuple[int, int]:
        return (self.width, self.height)


@dataclass(frozen=True)
class Rect:
    """屏幕矩形，坐标为左上角 (left, top) 到右下角 (right, bottom)。"""

    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def size(self) -> Size:
        return Size(self.width, self.height)

    @property
    def center(self) -> Point:
        return Point(
            x=(self.left + self.right) // 2,
            y=(self.top + self.bottom) // 2,
        )

    def contains(self, point: Point) -> bool:
        """点是否落在矩形内（含边界）。"""
        return (
            self.left <= point.x <= self.right
            and self.top <= point.y <= self.bottom
        )

    def to_tuple(self) -> tuple[int, int, int, int]:
        return (self.left, self.top, self.right, self.bottom)
