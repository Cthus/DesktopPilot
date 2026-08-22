"""Phase 1 验收: 浏览器元素操作闭环（click / type / get_text / wait_for）。

用 bilibili.com（国内可达）测真实页面操作 + 注入 DOM 测表单。
运行: python tests/acceptance_browser_phase1.py
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

from desktop_pilot.browser.manager import browser_manager


def main() -> None:
    ok = True

    print("1) 导航到 bilibili.com（国内可达，不依赖外网）...")
    r = browser_manager.navigate("bilibili.com")
    assert r["ok"], r
    print("   标题:", r["title"])

    print("2) get_text 读 <title> ...")
    text = browser_manager.get_text("title")
    print("   <title> =", text[:50])
    if not text:
        ok = False
        print("   !! title 为空")

    print("3) click 第一个链接 (a) ...")
    try:
        c = browser_manager.click("a")
        print("   点击:", c)
    except LookupError as e:
        print("   点击失败:", e)
        ok = False

    print("4) 等页面变化后读 URL ...")
    import time
    time.sleep(1.5)
    url = browser_manager.evaluate("location.href")
    print("   当前 URL:", str(url)[:70])

    print("5) 注入表单并测 type + wait_for ...")
    browser_manager.evaluate("document.body.innerHTML = '<input id=box><button id=go>Go</button>'")
    t = browser_manager.type_text("#box", "hello desktop_pilot")
    print("   type:", t)
    val = browser_manager.evaluate("document.querySelector('#box').value")
    print("   value =", val)
    if val != "hello desktop_pilot":
        ok = False
        print("   !! 输入值不符")

    w = browser_manager.wait_for_selector("#go", timeout=3)
    print("   wait_for:", w)

    print("6) 元素不存在时的错误处理 ...")
    try:
        browser_manager.click("#not-exist-xyz")
        print("   !! 应该抛 LookupError")
        ok = False
    except LookupError as e:
        print("   正确报错:", e)

    browser_manager.close()
    print("\nPHASE1", "PASS" if ok else "FAIL")


if __name__ == "__main__":
    main()
