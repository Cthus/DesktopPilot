"""5 行跑起来的最小 demo。

直接运行：`python examples/basic_usage.py`

做三件事：
1. 列出当前可见窗口（前 5 个）
2. 找标题含 "微信" 的窗口，列出其前 10 个控件（找不到就跳过，不崩）
3. 截全屏存到 screenshot.png
"""
from __future__ import annotations

from desktop_pilot import Desktop


def main() -> None:
    with Desktop() as bot:
        windows = bot.list_windows()
        print(f"找到 {len(windows)} 个可见窗口：")
        for w in windows[:5]:
            print(f"  - {w.name} @ {w.rect.to_tuple()}")

        # 尝试找微信（没有就优雅跳过）
        try:
            win = bot.find_window(title_contains="微信")
            print(f"\n微信窗口：{win.name}")
            elements = bot.list_elements(window=win)
            # list_elements 返回 [root]，所有后代通过 walk() 拿
            all_descendants = list(elements[0].walk()) if elements else []
            print(f"  共 {len(all_descendants)} 个控件，前 10 个：")
            for e in all_descendants[:10]:
                print(f"  - {e.control_type.value}: {e.name!r}")
        except Exception as exc:
            print(f"\n未找到微信窗口，跳过：{exc}")

        png = bot.screenshot()
        with open("screenshot.png", "wb") as fh:
            fh.write(png)
        print(f"\n截图已保存：screenshot.png ({len(png)} bytes)")


if __name__ == "__main__":
    main()
