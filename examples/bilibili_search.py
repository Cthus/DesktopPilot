"""Demo: 用 DesktopPilot 打开 B 站搜索 "玩机器" 并截图。

设计目标:
- 稳定: 不假设系统装了什么浏览器, 用 webbrowser.open 兜底
- 健壮: 每个步骤之间有 wait, 截图保存到固定目录
- 友好: 全程 print 进度, 出错提示明确

用法:
    python examples/bilibili_search.py
    # 或双击运行 (假设 .py 关联了 Python)
"""
from __future__ import annotations

import sys
import time
import webbrowser
from pathlib import Path

# 让脚本能找到 src/desktop_pilot (无需安装也能跑)
_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from desktop_pilot import Desktop  # noqa: E402

OUTPUT_DIR = _HERE / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

SEARCH_URL = "https://search.bilibili.com/all?keyword=%E7%8E%A9%E6%9C%BA%E5%99%A8"
SEARCH_KEYWORD = "玩机器"


def log(stage: str, msg: str = "") -> None:
    print(f"[{stage}] {msg}", flush=True)


def main() -> int:
    print("=" * 60)
    print(f"DesktopPilot demo: B站搜索 '{SEARCH_KEYWORD}'")
    print("=" * 60)

    # ---- 1. 用 webbrowser 打开 B 站搜索页 (绕过浏览器启动的脆弱性) ----
    log("1/5", f"打开 B 站搜索页: {SEARCH_URL}")
    opened = webbrowser.open(SEARCH_URL)
    if not opened:
        log("1/5", "⚠️  webbrowser 报告打开失败, 继续尝试")
    time.sleep(3.0)  # 等浏览器启动并加载完

    with Desktop() as bot:
        # ---- 2. 列出当前窗口确认浏览器已起 ----
        log("2/5", "当前所有顶层窗口:")
        wins = bot.list_windows()
        for w in wins[:10]:
            print(f"        • {w.title!r}  pid={w.pid}  rect={w.rect}")
        if not wins:
            log("2/5", "⚠️  没看到任何窗口, 等 2 秒再试")
            time.sleep(2.0)
            wins = bot.list_windows()

        # ---- 3. 找浏览器窗口, 滚到顶部, 截图 1 ----
        log("3/5", "滚到顶部, 截第 1 张图 (搜索结果顶部)")
        bot.key_press("ctrl+home")
        time.sleep(1.0)
        out1 = bot.screenshot_to_file(str(OUTPUT_DIR / "bilibili_search_玩机器_top.png"))
        log("3/5", f"✓ {out1}")

        # ---- 4. 滚动到中部, 截图 2 ----
        log("4/5", "滚到中部, 截第 2 张图 (更多结果)")
        bot.scroll("down", amount=8)
        time.sleep(1.5)
        out2 = bot.screenshot_to_file(str(OUTPUT_DIR / "bilibili_search_玩机器_mid.png"))
        log("4/5", f"✓ {out2}")

        # ---- 5. 再滚到下部, 截图 3 ----
        log("5/5", "滚到底部, 截第 3 张图 (全部结果)")
        bot.scroll("down", amount=8)
        time.sleep(1.5)
        out3 = bot.screenshot_to_file(str(OUTPUT_DIR / "bilibili_search_玩机器_bot.png"))
        log("5/5", f"✓ {out3}")

    print("=" * 60)
    print(f"完成 ✅  3 张截图保存在: {OUTPUT_DIR}")
    print("你可以把这些 PNG 发给我, 我用 vision_analyze 帮你看内容。")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n⏹  用户中断 (鼠标移到屏幕左上角也会触发)")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ 脚本异常: {e!r}")
        sys.exit(1)
