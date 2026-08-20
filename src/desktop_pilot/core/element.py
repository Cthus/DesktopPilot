"""屏幕元素数据模型。

三层：
- :class:`Element`：屏幕上能看到的东西的基类
- :class:`Control`：普通控件，带 value / children
- :class:`Window`：顶层窗口，带 hwnd / pid
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterator, Optional, TYPE_CHECKING

from .types import Rect

if TYPE_CHECKING:
    from .types import Point


class ControlType(Enum):
    """控件类型，值与 UIA/常见 UI 框架命名对齐。"""

    BUTTON = "Button"
    EDIT = "Edit"
    TEXT = "Text"
    LIST = "List"
    LISTITEM = "ListItem"
    CHECKBOX = "CheckBox"
    COMBOBOX = "ComboBox"
    MENU = "Menu"
    MENUITEM = "MenuItem"
    TAB = "Tab"
    TABITEM = "TabItem"
    LINK = "Hyperlink"
    IMAGE = "Image"
    RADIOBUTTON = "RadioButton"
    PROGRESSBAR = "ProgressBar"
    SLIDER = "Slider"
    TREE = "Tree"
    TREEITEM = "TreeItem"
    WINDOW = "Window"
    PANE = "Pane"
    CUSTOM = "Custom"
    UNKNOWN = "Unknown"


@dataclass
class Element:
    """屏幕上一个可见元素的基类。"""

    name: str
    control_type: ControlType
    rect: Rect
    enabled: bool = True
    visible: bool = True
    parent: Optional["Element"] = field(default=None, repr=False)

    # 子类（Control）覆写为真正的容器；基类没有子节点。
    children: list["Element"] = field(default_factory=list, repr=False)
    value: Optional[str] = None

    # 平台后端挂原始句柄/对象用，核心层不解释其含义。
    handle: object = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict:
        """序列化成可给 LLM 看的纯数据字典（不含 parent 避免环）。"""
        return {
            "name": self.name,
            "control_type": self.control_type.value,
            "rect": self.rect.to_tuple(),
            "enabled": self.enabled,
            "visible": self.visible,
            "value": self.value,
            "children": [c.to_dict() for c in self.children],
        }

    def find_child(
        self,
        name: Optional[str] = None,
        control_type: Optional[ControlType] = None,
        exact: bool = True,
    ) -> Optional["Element"]:
        """在子树里按名字 / 类型找第一个匹配（DFS）。

        - ``exact=True``：名字完全相等；``exact=False``：名字子串匹配。
        - 不会匹配自身。
        """
        for child in self.walk():
            if child is self:
                continue
            if name is not None:
                if exact:
                    if (child.name or "") != name:
                        continue
                else:
                    if name not in (child.name or ""):
                        continue
            if control_type is not None and child.control_type != control_type:
                continue
            return child
        return None

    def walk(self) -> Iterator["Element"]:
        """DFS 遍历自身及所有后代。"""
        yield self
        for child in self.children:
            yield from child.walk()

    def contains_point(self, point: "Point") -> bool:
        return self.rect.contains(point)


@dataclass
class Control(Element):
    """普通控件。当前仅为语义化占位，Element 已包含 children/value。"""


@dataclass
class Window(Control):
    """顶层窗口。额外带 Windows 句柄 hwnd 与进程 id pid。"""

    hwnd: Optional[int] = None
    pid: Optional[int] = None

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["hwnd"] = self.hwnd
        data["pid"] = self.pid
        return data
