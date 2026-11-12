"""给 classroom-preview.html 拍几张预览图，用来看建模效果。

四个机位各拍一张，顺便收集页面报错——CDN 拉不到或者 JS 写错都能第一时间发现。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "classroom-preview.html"
OUT = ROOT / "data"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
VIEWS = ["考生席", "考官特写", "脸部特写", "讲台", "侧墙", "全景"]


def main() -> int:
    if not HTML.exists():
        print(f"!! 找不到 {HTML}")
        return 1
    OUT.mkdir(exist_ok=True)

    errors: list[str] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=CHROME,
            headless=True,
            args=[
                "--use-gl=angle",
                "--use-angle=swiftshader",
                "--enable-unsafe-swiftshader",
                "--hide-scrollbars",
                "--window-size=1600,900",
                "--lang=zh-CN",
            ],
        )
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on(
            "console",
            lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None,
        )
        page.on("requestfailed", lambda r: errors.append(f"requestfailed: {r.url}"))

        page.goto(HTML.as_uri(), wait_until="load")
        try:
            page.wait_for_function("() => window.__sceneReady === true", timeout=25000)
            print("[ui] 场景初始化完成")
        except Exception:
            print("!! 场景没跑起来（window.__sceneReady 一直是 false）")

        time.sleep(2.0)
        page.wait_for_selector("#views button", timeout=10000)

        for i, name in enumerate(VIEWS):
            page.click(f"#views button:nth-child({i + 1})")
            time.sleep(1.4)
            path = OUT / f"classroom-{i + 1}-{name}.png"
            page.screenshot(path=str(path))
            print(f"[shot] {name} -> {path.name}")

        browser.close()

    if errors:
        print("\n!! 页面报错：")
        for line in errors[:10]:
            print(f"   - {line[:220]}")
        return 1

    print("\nRESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
