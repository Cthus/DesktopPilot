"""Phase 3 验收: 真实网站完整任务 —— B站搜索"玩机器"。

流程:导航 → 读 DOM 找到搜索框 → 填关键词 → 提交 → 等结果 → 读结果标题。
全程 DOM+JS,无截图无坐标。
运行: python tests/acceptance_browser_phase3.py
"""
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

from desktop_pilot.browser.manager import browser_manager


def main() -> None:
    print("1) 打开 B 站首页 ...")
    r = browser_manager.navigate("https://www.bilibili.com")
    print("   标题:", r.get("title", "?")[:50])

    print("2) 读 DOM 摘要(前几层) ...")
    d = browser_manager.get_dom()
    dom = (d or {}).get("dom", {}) if isinstance(d, dict) else {}
    print("   URL:", str(dom.get("url", "?"))[:60])
    body = dom.get("body", {})
    kids = body.get("children", [])
    print(f"   body 子元素 {len(kids)} 个:", [c.get("tag") for c in kids[:6]])

    print("3) 找到搜索输入框并输入'玩机器' ...")
    # B站搜索框 selector（nav-search-input 是其主搜索框）
    candidates = ["input.nav-search-input", "input[type=text][placeholder*='搜索']",
                  ".nav-search input", "input[placeholder]"]
    used = None
    for sel in candidates:
        try:
            t = browser_manager.type_text(sel, "玩机器")
            used = sel
            print(f"   输入成功 via {sel}: value={t.get('value','')[:20]}")
            break
        except LookupError:
            continue
        except Exception as e:
            print(f"   {sel} -> {type(e).__name__}: {str(e)[:60]}")
    if not used:
        # 兜底：用 JS 直接找第一个可见 text input
        js = """
        (() => {
          const inputs = [...document.querySelectorAll('input')].filter(i => i.offsetParent !== null);
          const el = inputs.find(i => (i.type==='text'||!i.type));
          if (!el) return null;
          el.value = '玩机器';
          el.dispatchEvent(new Event('input', {bubbles:true}));
          return el.className || el.id || 'injected';
        })()
        """
        res = browser_manager.evaluate(js)
        print("   兜底 JS 输入:", res)
        if not res:
            print("   !! 没找到可输入的搜索框")
            browser_manager.close()
            return

    print("4) 点击搜索按钮提交 ...")
    submitted = False
    for btn_sel in ["button.nav-search-btn", ".nav-search button", "button[type=submit]"]:
        try:
            c = browser_manager.click(btn_sel)
            submitted = True
            print(f"   提交 via {btn_sel}: {c}")
            break
        except LookupError:
            continue
        except Exception as e:
            print(f"   {btn_sel} -> {type(e).__name__}: {str(e)[:50]}")
    if not submitted:
        # 兜底：直接改 URL 跳搜索页
        print("   按钮未命中，直接导航到搜索 URL")
        browser_manager.navigate("https://search.bilibili.com/all?keyword=%E7%8E%A9%E6%9C%BA%E5%99%A8")
    time.sleep(3)

    print("5) 读取搜索结果页 ...")
    url = browser_manager.evaluate("location.href")
    title = browser_manager.evaluate("document.title")
    print("   URL:", str(url)[:70])
    print("   标题:", str(title)[:60])

    if "search.bilibili.com" in str(url):
        print("6) 读前几个视频标题 ...")
        js = """
        (() => {
          const items = [...document.querySelectorAll('.bili-video-card__info--tit, .video-list-item .title')]
            .slice(0,5).map(e => (e.textContent||'').trim()).filter(Boolean);
          return items;
        })()
        """
        titles = browser_manager.evaluate(js)
        if titles:
            for i, t in enumerate(titles):
                print(f"   [{i}] {str(t)[:50]}")
        else:
            print("   （选择器未命中，页面结构可能变化）")
    else:
        print("   （未跳到搜索结果页，可能需要另一种提交方式——记录现状）")

    browser_manager.close()
    print("\nPHASE3 DONE")


if __name__ == "__main__":
    main()
