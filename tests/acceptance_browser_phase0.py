"""Phase 0 验收: 浏览器 navigate + get_dom + evaluate + 连接复用。

运行: python tests/acceptance_browser_phase0.py
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

from desktop_pilot.browser.manager import browser_manager


def main() -> None:
    print("1) navigate example.com ...")
    try:
        r = browser_manager.navigate("example.com")
        print("   ok:", r.get("ok"), "| url:", str(r.get("url"))[:50])
    except Exception as e:
        print("   FAIL:", type(e).__name__, str(e)[:200])
        raise SystemExit(1)

    print("2) get_dom ...")
    d = browser_manager.get_dom()
    if isinstance(d, dict) and d.get("ok"):
        dom = d["dom"]
        print("   标题:", (dom or {}).get("title", "?"))
        body = (dom or {}).get("body", {})
        print("   body children:", len(body.get("children", [])))
    else:
        print("   dom raw:", str(d)[:200])

    print("3) evaluate JS ...")
    v = browser_manager.evaluate("document.querySelectorAll('a').length")
    print("   链接数:", v)

    print("4) 复用连接第二次 evaluate ...")
    v2 = browser_manager.evaluate("document.title")
    print("   title:", v2)

    browser_manager.close()
    print("\nPHASE0 PASS")


if __name__ == "__main__":
    main()
