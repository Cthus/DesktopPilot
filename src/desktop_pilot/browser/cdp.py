"""浏览器自动化核心：通过 Chrome DevTools Protocol (CDP) 控制浏览器。

不用截图/模拟点击，直接读 DOM + 用 JavaScript 操作——这是浏览器最可靠的自动化方式。
- 启动带远程调试端口的 Chrome/Edge
- 用 CDP 命令导航、执行 JS、读 DOM
- Hermes 拿到的是结构化 DOM，不是模糊的截图

CDP 关键接口：
- Page.navigate: 导航到 URL
- Runtime.evaluate: 执行任意 JS（读取 DOM、点击元素、填表单）
- Page.getFrameTree / DOM: 读文档结构
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import time
from typing import Any


# Chrome DevTools Protocol 方法名
CDP_PAGE_NAVIGATE = "Page.navigate"
CDP_RUNTIME_EVALUATE = "Runtime.evaluate"
CDP_PAGE_ENABLE = "Page.enable"
CDP_RUNTIME_ENABLE = "Runtime.enable"


class BrowserConnectionError(Exception):
    """无法连接浏览器调试端口时抛出。"""


def find_chrome() -> str | None:
    """找到可用的 Chrome/Edge 可执行文件路径。"""
    import os

    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


class BrowserCDP:
    """CDP 客户端：启动浏览器 + 连接调试端口 + 收发命令。"""

    def __init__(
        self,
        browser_path: str | None = None,
        port: int = 9222,
        headless: bool = False,
    ) -> None:
        self.browser_path = browser_path or find_chrome()
        if not self.browser_path:
            raise BrowserConnectionError("未找到 Chrome/Edge")
        self.port = port
        self.headless = headless
        self._proc: subprocess.Popen | None = None
        self._ws: Any = None  # websockets 连接
        self._page_url: str = ""
        self._debugger_url: str = ""
        self._msg_id: int = 0  # CDP 命令递增 id（id(self) 恒定会导致响应错配）

    # ------------------------------------------------------------------ #
    # 启动 / 关闭
    # ------------------------------------------------------------------ #
    def start(self) -> None:
        """启动带远程调试端口的 Chrome。"""
        import os
        import uuid

        # 每次用独立的 user-data-dir，避免 Chrome 检测到已有实例就转发给旧进程
        # （那样不会真正开新的远程调试端口）
        user_data = os.path.join(
            os.environ.get("TEMP", "/tmp"),
            f"desktop_pilot_chrome_{uuid.uuid4().hex[:8]}",
        )
        cmd = [
            self.browser_path,
            f"--remote-debugging-port={self.port}",
            f"--user-data-dir={user_data}",
            "--no-first-run",
            "--no-default-browser-check",
            "about:blank",
        ]
        if self.headless:
            cmd.insert(1, "--headless=new")
        # 后台启动，不阻塞
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

        # 等调试端口就绪
        for _ in range(30):
            try:
                import urllib.request

                with urllib.request.urlopen(
                    f"http://127.0.0.1:{self.port}/json", timeout=2
                ) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                time.sleep(0.5)
        self._debugger_url = self._get_page_debugger_url()

    def _get_page_debugger_url(self) -> str:
        """从调试端口拿到页面 WebSocket 地址。"""
        import urllib.request

        with urllib.request.urlopen(
            f"http://127.0.0.1:{self.port}/json", timeout=3
        ) as resp:
            targets = json.loads(resp.read().decode())
        for target in targets:
            if target.get("type") == "page":
                return target["webSocketDebuggerUrl"]
        raise BrowserConnectionError("调试端口无页面 target")

    async def connect(self) -> None:
        """建立 WebSocket 连接并启用必须的域。"""
        from websockets.asyncio.client import connect

        if not self._debugger_url:
            self._debugger_url = self._get_page_debugger_url()
        # websockets 15: asyncio.client.connect 才是返回连接对象的现代 API，
        # 直接放后台循环里长期持有。老的 await websockets.connect() 语义已变。
        self._ws = await connect(self._debugger_url)
        # 启用 Page 和 Runtime 域
        await self._send(CDP_PAGE_ENABLE, {})
        await self._send(CDP_RUNTIME_ENABLE, {})
        # 拿到当前 URL
        res = await self.evaluate("window.location.href")
        if res:
            self._page_url = str(res)

    async def _send(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """发送一条 CDP 命令并等响应。"""
        if self._ws is None:
            raise BrowserConnectionError("未连接调试端口（先调 connect）")
        self._msg_id += 1
        msg_id = self._msg_id
        payload = {"id": msg_id, "method": method, "params": params}
        await self._ws.send(json.dumps(payload))
        while True:
            raw = await self._ws.recv()
            data = json.loads(raw)
            if data.get("id") == msg_id:
                if "error" in data:
                    raise RuntimeError(f"CDP {method} 失败: {data['error']}")
                return data.get("result", {})
            # 忽略事件消息

    # ------------------------------------------------------------------ #
    # 高级操作（供工具调用）
    # ------------------------------------------------------------------ #
    async def navigate(self, url: str) -> dict[str, Any]:
        """导航到指定 URL。返回 {url, title, ready_state}。"""
        url = url if "://" in url else f"https://{url}"
        await self._send(CDP_PAGE_NAVIGATE, {"url": url})
        # 等页面加载完成
        ready = ""
        for _ in range(40):
            ready = await self.evaluate("document.readyState") or ""
            if ready == "complete":
                break
            await asyncio.sleep(0.25)
        title = await self.evaluate("document.title") or ""
        self._page_url = url
        return {"ok": True, "url": url, "title": str(title), "ready_state": str(ready)}

    async def evaluate(self, js: str) -> Any:
        """在页面上下文执行 JS，返回结果。"""
        if isinstance(js, str):
            expr = js
            return_by_value = True
        else:  # 已带 returnByValue 参数
            expr = js
            return_by_value = True
        res = await self._send(
            CDP_RUNTIME_EVALUATE,
            {
                "expression": expr,
                "returnByValue": return_by_value,
                "awaitPromise": True,
            },
        )
        res_val = res.get("result", {})
        if "value" in res_val:
            return res_val["value"]
        if "description" in res_val:
            return res_val["description"]
        return None

    async def get_dom_tree(self) -> dict[str, Any]:
        """获取当前页面的 DOM 树摘要（标题/URL/可交互元素）。"""
        script = """
        (() => {
            const summarize = (el, depth) => {
                if (depth > 3) return null;
                const tag = el.tagName ? el.tagName.toLowerCase() : '';
                const result = {
                    tag, depth,
                    id: el.id || '',
                    cls: typeof el.className === 'string' ? el.className : '',
                    text: (el.textContent || '').trim().slice(0, 60),
                };
                const children = [...el.children].filter(c => c.tagName).slice(0, 8);
                if (children.length) {
                    result.children = children.map(c => summarize(c, depth + 1));
                }
                return result;
            };
            return {
                url: location.href,
                title: document.title,
                body: summarize(document.body, 0),
            };
        })()
        """
        return await self.evaluate(script)

    # ------------------------------------------------------------------ #
    # 元素操作（JS 语义封装）
    # ------------------------------------------------------------------ #
    @staticmethod
    def _escape_selector(selector: str) -> str:
        """把 CSS selector 安全嵌入 JS 字符串。"""
        return selector.replace("\\", "\\\\").replace("'", "\\'")

    async def click(self, selector: str) -> dict[str, Any]:
        """按 CSS 选择器点击元素（触发原生 click 事件）。"""
        sel = self._escape_selector(selector)
        js = f"""
        (() => {{
            const el = document.querySelector('{sel}');
            if (!el) return {{ok: false, error: 'not found: {sel}'}};
            el.scrollIntoView({{block: 'center'}});
            el.click();
            return {{ok: true, tag: el.tagName.toLowerCase(), text: (el.textContent||'').trim().slice(0,60)}};
        }})()
        """
        result = await self.evaluate(js)
        if isinstance(result, dict) and not result.get("ok"):
            raise LookupError(result.get("error", f"元素不存在: {selector}"))
        return result if isinstance(result, dict) else {"ok": True}

    async def type_text(self, selector: str, text: str, clear: bool = True) -> dict[str, Any]:
        """往输入框填文本（设置 value + 触发 input/change 事件让框架感知）。"""
        sel = self._escape_selector(selector)
        esc_text = json.dumps(text)  # JSON 转义安全
        clear_js = "el.value = '';" if clear else ""
        js = f"""
        (() => {{
            const el = document.querySelector('{sel}');
            if (!el) return {{ok: false, error: 'not found: {sel}'}};
            el.focus();
            {clear_js}
            el.value = {esc_text};
            el.dispatchEvent(new Event('input', {{bubbles: true}}));
            el.dispatchEvent(new Event('change', {{bubbles: true}}));
            return {{ok: true, tag: el.tagName.toLowerCase(), value: String(el.value).slice(0,100)}};
        }})()
        """
        result = await self.evaluate(js)
        if isinstance(result, dict) and not result.get("ok"):
            raise LookupError(result.get("error", f"元素不存在: {selector}"))
        return result if isinstance(result, dict) else {"ok": True}

    async def get_text(self, selector: str) -> str:
        """读取元素的文本内容。"""
        sel = self._escape_selector(selector)
        js = f"""
        (() => {{
            const el = document.querySelector('{sel}');
            return el ? (el.textContent || '').trim() : null;
        }})()
        """
        result = await self.evaluate(js)
        if result is None:
            raise LookupError(f"元素不存在: {selector}")
        return str(result)

    async def wait_for_selector(self, selector: str, timeout: float = 10.0,
                                poll_interval: float = 0.5) -> dict[str, Any]:
        """轮询等待选择器出现，超时抛 WaitTimeoutError 语义的 LookupError。"""
        import time as _time

        deadline = _time.monotonic() + timeout
        while True:
            found = await self.evaluate(
                f"document.querySelector('{self._escape_selector(selector)}') !== null"
            )
            if found:
                return {"ok": True, "selector": selector}
            if _time.monotonic() >= deadline:
                raise TimeoutError(f"等待 {timeout:.1f}s 后选择器仍未出现: {selector}")
            await asyncio.sleep(poll_interval)

    async def close(self) -> None:
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except Exception:
                self._proc.kill()