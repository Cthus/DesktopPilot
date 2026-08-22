"""浏览器 CDP/Manager 单测（mock，不启动真实浏览器）。

覆盖：
- find_chrome 找到真实路径；
- navigate 补协议 / 保留完整 URL；
- evaluate 发送正确 CDP 命令；
- msg_id 递增（多次命令 id 不重复）；
- close 清理连接与进程。
"""
from __future__ import annotations

import asyncio
import json
import os

import pytest


class FakeWS:
    """模拟 websockets 连接：记录发送、按 id 回响应。"""

    def __init__(self, fail_on=None):
        self.sent = []
        self.closed = False
        self.fail_on = fail_on or set()

    async def send(self, payload):
        self.sent.append(json.loads(payload))

    async def recv(self):
        last = self.sent[-1]
        mid = last["id"]
        method = last["method"]
        if method in self.fail_on:
            return json.dumps({"id": mid, "error": {"message": "mock failure", "code": -1}})
        if method == "Page.navigate":
            resp = {"id": mid, "result": {"frameId": "f1"}}
        elif method == "Runtime.evaluate":
            # 返回递增值便于验证 id 匹配
            resp = {"id": mid, "result": {"result": {"type": "string", "value": f"resp-{mid}"}}}
        else:
            resp = {"id": mid, "result": {}}
        return json.dumps(resp)

    async def close(self):
        self.closed = True


class FakeProc:
    def __init__(self):
        self.terminated = False

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=0):
        return 0

    def kill(self):
        self.terminated = True


def _make_cdp():
    from desktop_pilot.browser.cdp import BrowserCDP

    fake = FakeWS()
    browser = BrowserCDP(browser_path="C:/fake/chrome.exe", port=9222)
    browser._ws = fake
    browser._debugger_url = "ws://fake"
    browser._proc = FakeProc()
    return browser, fake


def test_find_chrome_detects_real_path():
    from desktop_pilot.browser.cdp import find_chrome

    path = find_chrome()
    assert path is not None
    assert os.path.exists(path)


def test_navigate_adds_scheme():
    browser, fake = _make_cdp()
    r = asyncio.run(browser.navigate("example.com"))
    nav = [s for s in fake.sent if s["method"] == "Page.navigate"]
    assert nav[-1]["params"]["url"] == "https://example.com"
    assert r["ok"] is True
    assert r["url"] == "https://example.com"


def test_navigate_keeps_full_url():
    browser, fake = _make_cdp()
    asyncio.run(browser.navigate("http://a.b/c?d=1"))
    nav = [s for s in fake.sent if s["method"] == "Page.navigate"]
    assert nav[-1]["params"]["url"] == "http://a.b/c?d=1"


def test_evaluate_returns_value_and_ids_increment():
    browser, fake = _make_cdp()
    v1 = asyncio.run(browser.evaluate("1+1"))
    v2 = asyncio.run(browser.evaluate("2+2"))
    # 响应值包含 msg_id → 两次不同证明 id 递增且匹配正确
    assert v1 != v2
    evals = [s for s in fake.sent if s["method"] == "Runtime.evaluate"]
    ids = [s["id"] for s in evals]
    assert len(ids) >= 2 and len(set(ids)) == len(ids), "msg_id 必须唯一"


def test_click_missing_selector_raises():
    browser, fake = _make_cdp()

    # 让 evaluate 返回 not found 结构：改写 recv 行为
    class NotFoundWS(FakeWS):
        async def recv(self):
            last = self.sent[-1]
            payload = {"id": last["id"], "result": {"result": {"type": "object",
                       "value": {"ok": False, "error": "not found: x"}}}}
            return json.dumps(payload)

    browser._ws = NotFoundWS()
    with pytest.raises(LookupError):
        asyncio.run(browser.click("#nope"))


def test_wait_for_selector_timeout():
    browser, fake = _make_cdp()

    class AlwaysNullWS(FakeWS):
        async def recv(self):
            last = self.sent[-1]
            payload = {"id": last["id"], "result": {"result": {"type": "boolean", "value": False}}}
            return json.dumps(payload)

    browser._ws = AlwaysNullWS()
    with pytest.raises(TimeoutError):
        asyncio.run(browser.wait_for_selector("#never", timeout=0.3, poll_interval=0.05))


def test_close_cleans_up():
    browser, fake = _make_cdp()
    proc = browser._proc
    asyncio.run(browser.close())
    assert fake.closed is True
    assert proc.terminated is True


def test_send_without_connection_raises():
    from desktop_pilot.browser.cdp import BrowserCDP, BrowserConnectionError

    b = BrowserCDP(browser_path="x")
    with pytest.raises(BrowserConnectionError):
        asyncio.run(b._send("Runtime.evaluate", {}))
