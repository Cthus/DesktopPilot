"""DesktopPilot 统一日志。

设计目标：任何一次失败都要能定位。日志写 stderr（MCP stdio 场景下宿主会把
stderr 落盘——Hermes 写入 ``mcp-stderr.log``），默认打印控制流 `ERROR` /
`WARNING`；设环境变量 ``DESKTOP_PILOT_DEBUG=1`` 时开 DEBUG 并把完整 traceback
写进返回给调用方的结构化错误。

用法：:

    from ..core.logging import logger, debug_enabled

    logger.warning("...")
    if debug_enabled():
        logger.debug("detail")
"""
from __future__ import annotations

import logging
import os
import sys

_LOG_NAME = "desktop_pilot"


def _debug_from_env() -> bool:
    return os.environ.get("DESKTOP_PILOT_DEBUG", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _utf8_stderr():
    """把进程的 stderr 强制切到 UTF-8 写，避免 Windows locale(GBK) 下中文乱码。

    MCP 场景：Hermes 以子进程拉起本 server 并把 stderr 落盘（mcp-stderr.log），
    那里按 UTF-8 读；若我们这边用 GBK 写中文，日志里的每个字都变 �。这里顺手把
    整个 stderr 重配成 UTF-8（errors=replace 兜底），让中文、带音标等非 ASCII
    字符都能被正确读到。
    """
    stream = sys.stderr
    try:
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        pass
    return stream


def _build_logger() -> logging.Logger:
    log = logging.getLogger(_LOG_NAME)
    if not log.handlers:
        handler = logging.StreamHandler(_utf8_stderr())
        handler.setFormatter(
            logging.Formatter(
                "[%(asctime)s %(levelname)s %(name)s] %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        log.addHandler(handler)
        # 默认只出 WARNING 以上；DEBUG 模式全开。propagate=False 避免和宿主日志
        # （如 Hermes）重复交错。
        log.propagate = False
    log.setLevel(logging.DEBUG if _debug_from_env() else logging.WARNING)
    return log


logger = _build_logger()


def debug_enabled() -> bool:
    """是否处于调试模式（控制错误里是否携带完整 traceback / 环境上下文）。"""
    return logger.level <= logging.DEBUG