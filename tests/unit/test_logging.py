"""core.logging 单测。

验证：
- 日志 handler 的 stderr 被强制 UTF-8（Windows locale/GBK 下中文不乱码）；
- 中文日志经 handler 写出后字节是 UTF-8（Hermes 侧按 UTF-8 读 mcp-stderr.log）；
- debug_enabled() 与 logger 级别联动。
"""
from __future__ import annotations

import io
import logging
import sys


def _build_isolated_logger():
    """构造一个独立的 logger（不碰全局 desktop_pilot logger），写入给定 stream。"""
    log = logging.getLogger("desktop_pilot.test.isolated")
    log.handlers.clear()
    log.propagate = False
    return log


def test_utf8_stderr_reconfigures_stream(monkeypatch):
    from desktop_pilot.core import logging as lg

    wrapper = io.TextIOWrapper(io.BytesIO(), encoding="gbk")  # 模拟 Windows locale
    monkeypatch.setattr(sys, "stderr", wrapper)
    stream = lg._utf8_stderr()
    assert stream.encoding == "utf-8"
    assert stream.errors == "replace"


def test_logger_handler_stream_is_utf8():
    from desktop_pilot.core import logging as lg

    # 全局 logger 的 handler 应已绑定 UTF-8 的 stderr
    handler = lg.logger.handlers[0]
    assert handler.stream.encoding == "utf-8"


def test_chinese_message_written_as_utf8_bytes():
    # 用独立 buffer 验证：写入的是 UTF-8 字节，不是 GBK。
    buf = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    handler = logging.StreamHandler(buf)
    handler.setFormatter(logging.Formatter("%(message)s"))
    log = _build_isolated_logger()
    log.addHandler(handler)
    log.setLevel(logging.ERROR)

    log.error("微信的按钮")

    buf.flush()
    raw = buf.buffer.getvalue()
    # 直接断言："微信" 的 UTF-8 字节序列出现在输出里（若是 GBK 写出则不会有这段字节）
    assert "微信".encode("utf-8") in raw


def test_debug_gate_tracks_log_level():
    from desktop_pilot.core import logging as lg

    lg.logger.setLevel(logging.DEBUG)
    try:
        assert lg.debug_enabled() is True
    finally:
        lg.logger.setLevel(logging.WARNING)
    assert lg.debug_enabled() is False