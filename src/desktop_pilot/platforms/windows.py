"""Windows 后端（UIA + PyAutoGUI）。

这是 SDK 真正干活的部分：

- 用 pywinauto（UIA 后端）枚举窗口和控件树
- 用 PyAutoGUI 做鼠标 / 键盘 / 截图（坐标点击，走系统级输入）
- 用 ctypes 调 Win32 API 处理窗口激活

已知坑（务必留意）：
1. ``pyautogui.click`` 可能被其它进程抢焦点，点击前必须先 ``_activate_window``。
2. Godot / Unity / Electron 等自绘界面没有标准 UIA 子控件，``descendants()``
   可能为空，此时只能退回截图 / OCR（见 :mod:`desktop_pilot.vision`）。
3. ``SetForegroundWindow`` 经常被 Windows 拒绝，需要 ``AttachThreadInput``
   把前台线程的输入队列 attach 到当前线程再设置前台。
4. **高 DPI 缩放会让点击错位。** 模块导入时即调用 ``_enable_dpi_awareness()``
   把进程声明为 per-monitor DPI 感知，否则在 125%/150% 缩放下，截图、UIA 控件
   rect、pyautogui 点击会落在两套坐标系（逻辑 1536×864 vs 物理 1920×1080），
   表现为"截图能看清但点偏"。
"""
from __future__ import annotations

import functools
import io
import sys
import time
from ..core.element import ControlType, Element, Window
from ..core.exceptions import DesktopPilotError, PlatformError, WindowNotFoundError
from ..core.logging import debug_enabled, logger
from ..core.platform import Platform
from ..core.types import Rect

# pyautogui 在所有平台可导入（实际输入只在有 GUI 时生效）。
import pyautogui

# 输入类操作不要因为鼠标移到屏幕角落而抛 FailSafe。
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.05

# win32 相关依赖仅在 Windows 上存在；模块在非 Windows 也能被导入
# （Desktop 只会在 win32 下实例化本类，但测试需要 import 成功）。
try:  # pragma: no cover - 平台相关
    import ctypes
    from ctypes import wintypes

    import win32gui  # type: ignore
    from pywinauto import Application  # type: ignore

    _HAS_WIN32 = True
except Exception:  # pragma: no cover
    _HAS_WIN32 = False


def _enable_dpi_awareness() -> None:  # pragma: no cover - 真实 Win32 调用
    """把当前进程声明为 DPI 感知，统一截图 / UIA 控件 / 鼠标坐标。

    Windows 在高 DPI（如 125% 缩放）下，非 DPI 感知的进程会被系统**位图缩放**：
    它以为屏幕只有 1536×864，而物理像素是 1920×1080。结果就是截图里看到的点、
    pywinauto 读出的控件 rect、pyautogui 的鼠标点击落在两套坐标系，点击整体偏移
    （截图能看清，但点不到对应位置）。这里尽早把进程设为 per-monitor DPI 感知，
    让三者全部使用物理像素。

    按支持度逐级降级：Per-Monitor V2 (Win10 1703+) → Per-Monitor → System →
    旧版 SetProcessDPIAware。重复调用 / 已被外部声明过都安全。
    """
    for level in (-4, -3, -2):  # PER_MONITOR_AWARE_V2 / V1 / SYSTEM
        try:
            if ctypes.windll.shcore.SetProcessDpiAwareness(level) == 0:
                return
        except (OSError, AttributeError):
            continue
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (OSError, AttributeError):
        pass


if _HAS_WIN32:  # pragma: no cover - 平台相关
    _enable_dpi_awareness()


# --------------------------------------------------------------------------- #
# Win32 SendInput 结构，用于支持 Unicode / 中文输入。
# pyautogui.write() 在 Windows 上只能打 ASCII，非 ASCII 字符要走
# KEYEVENTF_UNICODE 把字符码直接塞进 SendInput。
#
# 注意：
# 1. INPUT 联合体必须包含 MOUSEINPUT（最大成员，32 字节），否则联合体偏小，
#    64 位下 sizeof(INPUT) 会是 32 而非原生 40，SendInput 会拒绝。
# 2. dwExtraInfo 是 ULONG_PTR（指针宽度），用 c_void_p，不能用 DWORD/POINTER。
# 3. 必须给 user32.SendInput 设 argtypes，否则 64 位下 LPINPUT 指针会被截断。
# --------------------------------------------------------------------------- #
if _HAS_WIN32:  # pragma: no cover - 平台相关
    _KEYEVENTF_UNICODE = 0x0004
    _KEYEVENTF_KEYUP = 0x0002
    _INPUT_KEYBOARD = 1

    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_void_p),
        ]

    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_void_p),
        ]

    class _HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        ]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT)]

    class _INPUT(ctypes.Structure):
        _fields_ = [
            ("type", wintypes.DWORD),
            ("union", _INPUTUNION),
        ]
else:
    _INPUT = None  # type: ignore[assignment]


# pywinauto/UIA control_type 字符串 -> 我们的 ControlType。
# UIA 的 localized_control_type 可能是中文，这里用稳定的 control_type
# （pywinauto 的 element_info.control_type 是英文，如 "Button"）。
_TYPE_MAP = {
    "Button": ControlType.BUTTON,
    "Edit": ControlType.EDIT,
    "Document": ControlType.EDIT,
    "Text": ControlType.TEXT,
    "Static": ControlType.TEXT,
    "List": ControlType.LIST,
    "ListBox": ControlType.LIST,
    "ListItem": ControlType.LISTITEM,
    "CheckBox": ControlType.CHECKBOX,
    "ComboBox": ControlType.COMBOBOX,
    "Menu": ControlType.MENU,
    "MenuItem": ControlType.MENUITEM,
    "Tab": ControlType.TAB,
    "TabItem": ControlType.TABITEM,
    "Hyperlink": ControlType.LINK,
    "Image": ControlType.IMAGE,
    "RadioButton": ControlType.RADIOBUTTON,
    "ProgressBar": ControlType.PROGRESSBAR,
    "Slider": ControlType.SLIDER,
    "Tree": ControlType.TREE,
    "TreeItem": ControlType.TREEITEM,
    "Window": ControlType.WINDOW,
    "Pane": ControlType.PANE,
    "Custom": ControlType.CUSTOM,
}

# "ctrl+c" / "ctrl+v" / "alt+f4" 之类组合键 -> pyautogui 按键名。
_MOD_ALIASES = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "cmd": "win",
    "win": "win",
    "windows": "win",
    "alt": "alt",
    "shift": "shift",
    "option": "alt",
}


def _map_control_type(raw: str | None) -> ControlType:
    if not raw:
        return ControlType.UNKNOWN
    return _TYPE_MAP.get(raw, ControlType.UNKNOWN)


def _safe_rect(rect_obj) -> Rect:
    """把 pywinauto rectangle / win32 rect 转成我们的 Rect，容错。"""
    try:
        return Rect(
            left=int(rect_obj.left),
            top=int(rect_obj.top),
            right=int(rect_obj.right),
            bottom=int(rect_obj.bottom),
        )
    except Exception:
        try:
            l, t, r, b = rect_obj
            return Rect(int(l), int(t), int(r), int(b))
        except Exception:
            return Rect(0, 0, 0, 0)


def _contextualize(method):
    """装饰 WindowsPlatform 的公共 I/O 方法：失败时自动附上环境快照。

    - 已经是 DesktopPilotError：原地往 ``details["env"]`` 塞环境快照（幂等），
      保留原有错误语义（WindowNotFound / ElementNotFound 仍是原类型）；
    - 参数校验类错误（ValueError/TypeError/KeyError）：保持原样，不进快照；
    - 其它外部异常（pywinauto COM / pyautogui）：转成带环境快照的
      :class:`PlatformError`，这样分发边界能正确归类，而不是裸 ``InternalError``。

    环境快照（:meth:`WindowsPlatform._context_snapshot`）含屏幕分辨率、DPI 缩放、
    前台窗口、光标位置，是排障"点偏 / 发错窗口"的第一手信息。
    """
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except (KeyboardInterrupt, SystemExit):
            raise
        except DesktopPilotError as exc:
            exc.details.setdefault("env", self._context_snapshot())
            raise
        except (ValueError, TypeError, KeyError):
            raise
        except Exception as exc:  # noqa: BLE001 - 外来异常统一包装
            raise PlatformError(
                f"{type(exc).__name__}: {exc}",
                details={"env": self._context_snapshot()},
            ) from exc

    return wrapper


class WindowsPlatform(Platform):
    """基于 pywinauto(UIA) + PyAutoGUI 的 Windows 后端。"""

    def __init__(self) -> None:
        if not _HAS_WIN32:  # pragma: no cover - 仅在缺依赖时触发
            raise PlatformError(
                "Windows 后端需要 pywinauto 和 pywin32："
                "pip install pywinauto pywin32"
            )
        # hwnd -> Application 连接缓存，避免重复 connect。
        self._apps: dict[int, "Application"] = {}
        # use_last_error=True 才能用 ctypes.get_last_error() 拿到真实错误码。
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        # 64 位下必须声明 argtypes，否则 LPINPUT 指针会被当成 32 位截断，
        # 导致 SendInput 静默失败（返回 0）。
        if not getattr(WindowsPlatform, "_sendinput_configured", False):
            self._user32.SendInput.argtypes = [
                wintypes.UINT,
                ctypes.c_void_p,
                ctypes.c_int,
            ]
            self._user32.SendInput.restype = wintypes.UINT
            # 旧实例可能持有的是不带 argtypes 的 user32，这里类级标记已足够。
            WindowsPlatform._sendinput_configured = True

    # ------------------------------------------------------------------ #
    # 内部工具
    # ------------------------------------------------------------------ #
    def _context_snapshot(self) -> dict[str, Any]:
        """抓一份排障用的环境快照，失败时附在错误的 ``details["env"]`` 里。

        全防御式：任一探测失败（缺属性 / COM 异常 / 无窗口）就跳过该项，
        保证"为了报错"本身不会再抛错。视角：屏幕分辨率、DPI 缩放、
        前台窗口、光标位置、解释器与库版本——调试"点偏 / 发错窗口"的第一手信息。
        """
        snap: dict[str, Any] = {}
        try:
            snap["screen_size"] = [
                self._user32.GetSystemMetrics(0),
                self._user32.GetSystemMetrics(1),
            ]
        except Exception:
            pass
        try:
            hdc = self._user32.GetDC(0)
            if hdc:
                dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
                self._user32.ReleaseDC(0, hdc)
                snap["dpi_scale_pct"] = int(round(dpi / 96 * 100))
        except Exception:
            pass
        try:
            fg = self._user32.GetForegroundWindow()
            if fg:
                buf = ctypes.create_unicode_buffer(512)
                self._user32.GetWindowTextW(fg, buf, 512)
                snap["foreground"] = {"hwnd": fg, "title": buf.value}
        except Exception:
            pass
        try:
            pt = wintypes.POINT()
            if self._user32.GetCursorPos(ctypes.byref(pt)):
                snap["cursor"] = (pt.x, pt.y)
        except Exception:
            pass
        try:
            snap["python"] = sys.version.split()[0]
            import desktop_pilot as _dp

            snap["desktop_pilot"] = getattr(_dp, "__version__", "unknown")
        except Exception:
            pass
        return snap

    def _app_for(self, hwnd: int) -> "Application":  # pragma: no cover - 真实 UIA 连接
        app = self._apps.get(hwnd)
        if app is None:
            app = Application(backend="uia").connect(handle=hwnd)
            self._apps[hwnd] = app
        return app

    def _activate_window(self, hwnd: int) -> None:  # pragma: no cover - 真实前台切换
        """把 hwnd 拉到前台。

        ``SetForegroundWindow`` 在多种情况下会被 Windows 静默拒绝，
        用 AttachThreadInput 把当前线程 attach 到当前前台线程再设置可绕过。
        """
        if not hwnd:
            return
        try:
            SW_RESTORE = 9
            self._user32.ShowWindow(hwnd, SW_RESTORE)

            fg = self._user32.GetForegroundWindow()
            if fg == hwnd:
                return

            fg_tid = self._user32.GetWindowThreadProcessId(fg, 0)
            kernel32 = ctypes.windll.kernel32
            me_tid = kernel32.GetCurrentThreadId()

            if fg_tid != me_tid:
                self._user32.AttachThreadInput(fg_tid, me_tid, True)
                self._user32.SetForegroundWindow(hwnd)
                self._user32.SetFocus(hwnd)
                self._user32.BringWindowToTop(hwnd)
                self._user32.AttachThreadInput(fg_tid, me_tid, False)
            else:
                self._user32.SetForegroundWindow(hwnd)
        except Exception as exc:
            # 激活失败不直接抛，后续点击仍可能生效；记录到 details。
            raise PlatformError(
                f"激活窗口 {hwnd} 失败: {exc}",
                details={"hwnd": hwnd},
            ) from exc
        time.sleep(0.2)

    def _get_pid(self, hwnd: int) -> int | None:  # pragma: no cover - 真实 Win32 调用
        """通过 user32.GetWindowThreadProcessId 取窗口所属进程 id。"""
        lpdw = ctypes.c_ulong(0)
        self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(lpdw))
        return int(lpdw.value) if lpdw.value else None

    def _send_unicode_unit(self, unit: int, flags: int) -> None:
        inp = _INPUT(
            type=_INPUT_KEYBOARD,
            union=_INPUTUNION(
                ki=_KEYBDINPUT(
                    wVk=0,
                    wScan=unit,
                    dwFlags=flags,
                    time=0,
                    dwExtraInfo=None,
                )
            ),
        )
        sent = self._user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))
        if sent != 1:
            err = ctypes.get_last_error()
            raise PlatformError(
                f"SendInput 失败 (scan=0x{unit:04x}, flags=0x{flags:x}), "
                f"GetLastError={err}",
                details={"scan": unit, "flags": flags, "last_error": err},
            )

    def _type_unicode(self, text: str) -> None:  # pragma: no cover - 真实键盘输入
        """用 SendInput + KEYEVENTF_UNICODE 输入任意 Unicode 字符（含中文）。

        pyautogui.write() 只支持 ASCII，所以非 ASCII 字符走这里：
        对每个码点发一次 key-down 和一次 key-up。BMP 外字符（emoji 等）
        用 UTF-16 代理对（surrogate pair）发送。
        """
        for ch in text:
            code = ord(ch)
            if 0x10000 <= code <= 0x10FFFF:
                code -= 0x10000
                surrogates = (0xD800 + (code >> 10), 0xDC00 + (code & 0x3FF))
            else:
                surrogates = (code,)
            for unit in surrogates:
                self._send_unicode_unit(unit, _KEYEVENTF_UNICODE)
                self._send_unicode_unit(
                    unit, _KEYEVENTF_UNICODE | _KEYEVENTF_KEYUP
                )

    def _win32_to_window(self, hwnd: int) -> Window:  # pragma: no cover - 真实 Win32 调用
        """从 hwnd 构造 Window 对象（轻量，不读控件树）。"""
        try:
            title = win32gui.GetWindowText(hwnd)
        except Exception:
            title = ""
        try:
            rect = _safe_rect(win32gui.GetWindowRect(hwnd))
        except Exception:
            rect = Rect(0, 0, 0, 0)
        try:
            pid = self._get_pid(hwnd)
        except Exception:
            pid = None
        return Window(
            name=title or "",
            control_type=ControlType.WINDOW,
            rect=rect,
            hwnd=hwnd,
            pid=pid,
            handle=hwnd,
        )

    def _build_element_tree(self, wrapper) -> Element:  # pragma: no cover - 真实 UIA 遍历
        """递归把 pywinauto UIA wrapper 转成 Element 树。"""
        info = wrapper.element_info
        ctrl_type = _map_control_type(getattr(info, "control_type", None))
        name = getattr(info, "name", "") or ""
        rect = _safe_rect(wrapper.rectangle() if hasattr(wrapper, "rectangle") else info.rectangle)

        value = None
        if ctrl_type == ControlType.EDIT:
            try:
                value = wrapper.window_text()
            except Exception:
                value = None
        elif ctrl_type in (ControlType.TEXT, ControlType.BUTTON, ControlType.MENUITEM,
                           ControlType.LISTITEM, ControlType.CHECKBOX):
            try:
                value = wrapper.window_text()
            except Exception:
                value = None

        try:
            enabled = bool(wrapper.is_enabled())
        except Exception:
            enabled = True
        try:
            visible = bool(wrapper.is_visible())
        except Exception:
            visible = True

        elem = Element(
            name=name,
            control_type=ctrl_type,
            rect=rect,
            enabled=enabled,
            visible=visible,
            value=value,
            handle=wrapper,
        )

        children: list[Element] = []
        try:
            child_wrappers = wrapper.children()
        except Exception:
            child_wrappers = []
        for cw in child_wrappers:
            child = self._build_element_tree(cw)
            child.parent = elem
            children.append(child)
        elem.children = children
        return elem

    # ------------------------------------------------------------------ #
    # Platform API
    # ------------------------------------------------------------------ #
    def screenshot(self) -> bytes:  # pragma: no cover - 真实屏幕截图
        img = pyautogui.screenshot()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def list_windows(self) -> list[Window]:  # pragma: no cover - 真实窗口枚举
        windows: list[Window] = []

        def _cb(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return True
            title = win32gui.GetWindowText(hwnd)
            if not title or not title.strip():
                return True
            # 过滤掉没有边框的工具窗口 / 零尺寸窗口。
            try:
                l, t, r, b = win32gui.GetWindowRect(hwnd)
                if r - l <= 0 or b - t <= 0:
                    return True
            except Exception:
                return True
            windows.append(self._win32_to_window(hwnd))
            return True

        try:
            win32gui.EnumWindows(_cb, None)
        except Exception as exc:
            raise PlatformError(f"枚举窗口失败: {exc}") from exc
        return windows

    def find_window(
        self,
        title: str | None = None,
        title_contains: str | None = None,
        pid: int | None = None,
    ) -> Window:  # pragma: no cover - 依赖 list_windows
        candidates = self.list_windows()
        for w in candidates:
            if title is not None and w.name != title:
                continue
            if title_contains is not None and title_contains not in (w.name or ""):
                continue
            if pid is not None and w.pid != pid:
                continue
            return w
        raise WindowNotFoundError(
            f"找不到匹配的窗口: title={title!r}, "
            f"title_contains={title_contains!r}, pid={pid}",
            details={"title": title, "title_contains": title_contains, "pid": pid},
        )

    def list_elements(self, window: Window) -> list[Element]:  # pragma: no cover - 真实 UIA 遍历
        if not window.hwnd:
            raise PlatformError("window.hwnd 缺失，无法读取控件树", details={"window": window.name})
        try:
            app = self._app_for(window.hwnd)
            top = app.window(handle=window.hwnd)
            root = self._build_element_tree(top)
        except WindowNotFoundError:
            raise
        except Exception as exc:
            raise PlatformError(
                f"读取窗口控件树失败: {exc}",
                details={"window": window.name, "hwnd": window.hwnd},
            ) from exc

        # 让根元素回指 window，保证 parent 链完整。
        root.parent = window
        return [root]

    # ------------------------------------------------------------------ #
    # 鼠标
    # ------------------------------------------------------------------ #
    _BUTTONS = ("left", "right", "middle")

    @staticmethod
    def _norm_button(button: str) -> str:
        b = (button or "left").strip().lower()
        if b not in WindowsPlatform._BUTTONS:
            raise ValueError(f"未知鼠标键: {button!r}（应为 left/right/middle）")
        return b

    def _click(self, x: int, y: int, button: str, clicks: int, hwnd: int | None = None) -> None:  # pragma: no cover - 真实鼠标
        # 优先激活调用方指定的窗口；否则激活当前前台窗口——避免 SendInput
        # 被 Windows 路由到错误的应用（pyautogui.click 的已知坑）。
        if hwnd is None:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
        self._activate_window(hwnd)
        try:
            pyautogui.click(x=x, y=y, button=button, clicks=clicks, interval=0.05)
        except Exception as exc:
            raise PlatformError(f"点击 ({x},{y}) 失败: {exc}") from exc

    def move_to(self, x: int, y: int) -> None:  # pragma: no cover
        try:
            pyautogui.moveTo(x, y)
        except Exception as exc:
            raise PlatformError(f"移动到 ({x},{y}) 失败: {exc}") from exc

    def click(self, x: int, y: int) -> None:  # pragma: no cover
        self._click(x, y, button="left", clicks=1)

    def double_click(self, x: int, y: int) -> None:  # pragma: no cover
        self._click(x, y, button="left", clicks=2)

    def right_click(self, x: int, y: int) -> None:  # pragma: no cover
        self._click(x, y, button="right", clicks=1)

    def middle_click(self, x: int, y: int) -> None:  # pragma: no cover
        self._click(x, y, button="middle", clicks=1)

    def mouse_down(self, button: str = "left", x: int | None = None, y: int | None = None) -> None:  # pragma: no cover
        b = self._norm_button(button)
        if x is not None and y is not None:
            try:
                pyautogui.moveTo(x, y)
            except Exception as exc:
                raise PlatformError(f"移动到 ({x},{y}) 失败: {exc}") from exc
        self._ensure_foreground()
        try:
            pyautogui.mouseDown(button=b)
        except Exception as exc:
            raise PlatformError(f"按下 {b} 键失败: {exc}") from exc

    def mouse_up(self, button: str = "left", x: int | None = None, y: int | None = None) -> None:  # pragma: no cover
        b = self._norm_button(button)
        if x is not None and y is not None:
            try:
                pyautogui.moveTo(x, y)
            except Exception as exc:
                raise PlatformError(f"移动到 ({x},{y}) 失败: {exc}") from exc
        self._ensure_foreground()
        try:
            pyautogui.mouseUp(button=b)
        except Exception as exc:
            raise PlatformError(f"松开 {b} 键失败: {exc}") from exc

    # ------------------------------------------------------------------ #
    # 键盘
    # ------------------------------------------------------------------ #
    def _ensure_foreground(self) -> None:
        """重新激活当前前台窗口——保证后续 SendInput 落到正确应用。

        pyautogui 内部用 SendInput，Windows 会把输入路由到前台窗口。
        在 Hermes CLI 环境下，terminal 工具每次开 powershell 都会抢焦点，
        所以每次鼠标键盘操作前必须"再确认一次"前台。
        """
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if hwnd:
            self._activate_window(hwnd)

    def type_text(self, text: str) -> None:  # pragma: no cover - 真实键盘输入
        """逐字输入文本。

        ASCII 可打印字符走 pyautogui（稳定快速）；遇到非 ASCII（中文、
        带重音字母等）改用 SendInput KEYEVENTF_UNICODE，因为
        pyautogui.write() 在 Windows 上不支持这些字符。
        """
        if not text:
            return
        self._ensure_foreground()
        # 把文本按“可被 pyautogui 打印的 ASCII 连续段”与“非 ASCII 段”切开，
        # ASCII 段批量 write，非 ASCII 段逐个走 Unicode 注入。
        buf = ""
        try:
            for ch in text:
                if ord(ch) < 128 and ch.isprintable() and ch not in "\t\n\r":
                    buf += ch
                else:
                    if buf:
                        pyautogui.write(buf, interval=0.005)
                        buf = ""
                    if ch in "\n\r":
                        self.key_press("enter")
                    elif ch == "\t":
                        self.key_press("tab")
                    else:
                        self._type_unicode(ch)
            if buf:
                pyautogui.write(buf, interval=0.005)
        except Exception as exc:
            raise PlatformError(f"输入文本失败: {exc}") from exc

    def key_press(self, key: str) -> None:
        """按键。支持单键 ``"enter"`` 和组合 ``"ctrl+c"`` / ``"alt+f4"``。"""
        if not key:
            return
        self._ensure_foreground()
        expr = key.strip().lower()
        try:
            if "+" in expr:
                parts = [p.strip() for p in expr.split("+") if p.strip()]
                if len(parts) < 2:
                    raise ValueError(f"无效的组合键: {key!r}")
                *mods, final = parts
                mod_names = [_MOD_ALIASES.get(m, m) for m in mods]
                pyautogui.hotkey(*mod_names, final)
            else:
                pyautogui.press(expr)
        except Exception as exc:
            raise PlatformError(f"按键 {key!r} 失败: {exc}") from exc

    def scroll(
        self,
        direction: str,
        amount: int = 3,
        x: int | None = None,
        y: int | None = None,
    ) -> None:
        d = direction.lower()
        # 滚轮作用于光标所在窗口/控件：给定坐标就先把光标移过去。
        if x is not None and y is not None:
            try:
                pyautogui.moveTo(x, y)
            except Exception as exc:  # pragma: no cover
                raise PlatformError(f"移动到 ({x},{y}) 失败: {exc}") from exc
        self._ensure_foreground()
        try:
            if d == "up":
                pyautogui.scroll(amount)
            elif d == "down":
                pyautogui.scroll(-amount)
            elif d in ("left", "right"):
                # 水平滚动：优先用 pyautogui.hscroll；老版本没有，
                # 退回 shift+竖直滚轮（多数应用把 shift+滚轮映射为水平滚动）。
                sign = amount if d == "right" else -amount
                if hasattr(pyautogui, "hscroll"):
                    pyautogui.hscroll(sign)
                else:  # pragma: no cover - 取决于 pyautogui 版本
                    pyautogui.keyDown("shift")
                    pyautogui.scroll(sign)
                    pyautogui.keyUp("shift")
            else:
                raise ValueError(f"未知滚动方向: {direction!r}")
        except ValueError:
            raise
        except Exception as exc:  # pragma: no cover
            raise PlatformError(f"滚动失败: {exc}") from exc

    def drag(self, x1: int, y1: int, x2: int, y2: int) -> None:
        try:
            pyautogui.moveTo(x1, y1)
            self._ensure_foreground()
            pyautogui.mouseDown(button="left")
            pyautogui.moveTo(x2, y2, duration=0.2)
            pyautogui.mouseUp(button="left")
        except Exception as exc:  # pragma: no cover
            raise PlatformError(
                f"拖拽 ({x1},{y1})->({x2},{y2}) 失败: {exc}"
            ) from exc

    def close(self) -> None:
        # pywinauto Application 没有需要显式释放的资源；清掉缓存即可。
        self._apps.clear()


# 给所有真实 I/O 的公共方法挂上环境快照：失败时 details["env"] 自动带上
# 屏幕/DPI/前台/光标（见 _context_snapshot 与 _contextualize）。集中 rewrap，
# 避免在 17 处方法上各写一遍装饰器。close 是纯内存操作，无需包裹。
_CONTEXTUALIZED_METHODS = (
    "screenshot",
    "list_windows",
    "find_window",
    "list_elements",
    "move_to",
    "click",
    "double_click",
    "right_click",
    "middle_click",
    "mouse_down",
    "mouse_up",
    "type_text",
    "key_press",
    "scroll",
    "drag",
    "_activate_window",
    "_ensure_foreground",
)
for _method_name in _CONTEXTUALIZED_METHODS:
    setattr(
        WindowsPlatform,
        _method_name,
        _contextualize(getattr(WindowsPlatform, _method_name)),
    )


__all__ = ["WindowsPlatform"]
