"""演示完整流程：打开浏览器 → 聚焦地址栏 → 输入 URL → 回车访问。

运行：`python examples/open_browser.py`

注意：这是一个真实控制你电脑的例子，运行前请保存好工作。
不同系统/语言环境下窗口标题不同（Chrome / Edge / "Google Chrome"），
这里用子串匹配，并对找不到的情况做了容错。
"""
from __future__ import annotations

import argparse
import sys
import time

from desktop_pilot import Desktop, WindowNotFoundError

# 想访问的地址
TARGET_URL = "https://www.python.org"

# 按优先级匹配的浏览器标题关键字
_BROWSER_KEYWORDS = ("Google Chrome", "Chrome", "Microsoft Edge", "Edge", "Firefox")


def find_browser(bot: Desktop, timeout: float = 15.0):
    """轮询直到某个浏览器窗口出现，返回 Window；超时返回 None。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for kw in _BROWSER_KEYWORDS:
            try:
                return bot.find_window(title_contains=kw)
            except WindowNotFoundError:
                continue
        time.sleep(0.5)
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="DesktopPilot 浏览器自动化示例")
    parser.add_argument(
        "--url", default=TARGET_URL, help=f"要访问的 URL（默认 {TARGET_URL}）"
    )
    parser.add_argument(
        "--no-close",
        action="store_true",
        help="访问完成后不要关闭浏览器标签（默认保留）",
    )
    args = parser.parse_args()

    with Desktop() as bot:
        # 1. 用 Win+R 启动 Chrome（机器上没装可改成 msedge / firefox）
        print("1) Win+R 启动 chrome ...")
        bot.key_press("win+r")
        time.sleep(0.8)
        bot.type_text("chrome")
        bot.key_press("enter")
        time.sleep(2.5)

        # 2. 等浏览器窗口出现
        print("2) 等待浏览器窗口出现 ...")
        win = find_browser(bot, timeout=15)
        if win is None:
            print("   没找到浏览器窗口，退出。请确认已安装 Chrome/Edge/Firefox。")
            return
        print(f"   浏览器窗口：{win.name!r}")

        # 3. 聚焦地址栏。
        # 现代浏览器（Chrome/Edge/Firefox）都用 Ctrl+L 聚焦地址栏，
        # 比按名字找 Edit 控件更稳——浏览器的地址栏常是自绘/无名控件。
        print("3) Ctrl+L 聚焦地址栏 ...")
        # 先激活窗口，避免快捷键发到别的进程。
        activator = getattr(bot.platform, "_activate_window", None)
        if callable(activator) and win.hwnd:
            activator(win.hwnd)
        bot.key_press("ctrl+l")
        time.sleep(0.4)

        # 4. 输入 URL 并访问
        print(f"4) 输入 {args.url} 并回车 ...")
        bot.type_text(args.url)
        time.sleep(0.2)
        bot.key_press("enter")

        # 5. 等页面加载，截图证明
        print("5) 等待页面加载并截图 ...")
        time.sleep(4.0)
        png = bot.screenshot()
        with open("browser_demo.png", "wb") as fh:
            fh.write(png)
        print(f"   截图已保存：browser_demo.png ({len(png)//1024} KB)")

        if args.no_close:
            print("完成，浏览器保留。")
        else:
            # 不杀整个浏览器进程，只关闭刚打开的这个窗口（Ctrl+W 关当前标签）。
            print("6) 关闭当前标签（Ctrl+W）...")
            bot.key_press("ctrl+w")
            time.sleep(0.5)
            print("完成。")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
