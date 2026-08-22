"""浏览器管理器：在后台事件循环里保持一个 CDP 连接，供多个工具调用复用。

CDP 基于 asyncio，而工具 handler 是同步的。用一个守护线程跑事件循环，
所有浏览器操作（含建连）都提交到该循环内执行——连接对象与创建它的循环
同线程归属，避免跨线程问题。工具调用通过 run_in_loop 等待结果。
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import threading
from typing import Any, Callable, Coroutine, Optional


class BrowserManager:
    """单例：后台循环 + 惰性启动浏览器 + 复用连接。"""

    _instance: Optional["BrowserManager"] = None

    def __init__(self, browser_path: str | None = None) -> None:
        self._browser_path = browser_path
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._cdp: Any = None
        self._lock = threading.Lock()

    @classmethod
    def get(cls, browser_path: str | None = None) -> "BrowserManager":
        if cls._instance is None:
            cls._instance = cls(browser_path)
        return cls._instance

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #
    def _ensure_loop(self) -> None:
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(
                target=self._loop.run_forever,
                name="desktop-pilot-browser",
                daemon=True,
            )
            self._thread.start()

    def run_in_loop(
        self,
        coro_factory: Callable[[], Coroutine[Any, Any, Any]],
        timeout: float = 30.0,
    ) -> Any:
        """把协程工厂提交到后台循环执行并等结果。

        注意：coro_factory 在后台循环线程里被调用，保证协程绑定正确的 loop。
        """
        self._ensure_loop()
        assert self._loop is not None
        fut: concurrent.futures.Future = asyncio.run_coroutine_threadsafe(
            coro_factory(), self._loop
        )
        return fut.result(timeout=timeout)

    async def _async_connect(self) -> Any:
        """在后台循环内完成启动+建连（连接归属本循环）。"""
        from .cdp import BrowserCDP

        cdp = BrowserCDP(browser_path=self._browser_path)
        # start() 是同步的（起子进程 + HTTP 探测端口），在线程池里跑避免阻塞循环
        await asyncio.to_thread(cdp.start)
        await cdp.connect()
        return cdp

    def ensure_browser(self) -> None:
        """惰性启动 CDP；已连则复用（健康检查在循环内做）。"""
        with self._lock:
            if self._cdp is not None:
                try:
                    # 健康检查：在循环内跑一条轻量 evaluate
                    self.run_in_loop(self._cdp.evaluate, timeout=5)("1")
                    return
                except Exception:
                    # 连接断了 → 关掉旧的重建
                    try:
                        self.run_in_loop(self._cdp.close, timeout=5)
                    except Exception:
                        pass
                    self._cdp = None

            self._ensure_loop()
            self._cdp = self.run_in_loop(self._async_connect, timeout=60)

    # ------------------------------------------------------------------ #
    # 浏览器操作（同步入口，供工具 handler 调用）
    # ------------------------------------------------------------------ #
    def navigate(self, url: str) -> dict[str, Any]:
        self.ensure_browser()
        return self.run_in_loop(lambda: self._cdp.navigate(url), timeout=60)

    def get_dom(self) -> dict[str, Any]:
        self.ensure_browser()
        return self.run_in_loop(self._cdp.get_dom_tree, timeout=30)

    def evaluate(self, js: str) -> Any:
        self.ensure_browser()
        return self.run_in_loop(lambda: self._cdp.evaluate(js), timeout=30)

    def close(self) -> None:
        with self._lock:
            if self._cdp is not None:
                try:
                    self.run_in_loop(self._cdp.close, timeout=5)
                except Exception:
                    pass
                self._cdp = None


# 全局单例（MCP server 进程里复用）
browser_manager = BrowserManager()
