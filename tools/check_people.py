"""用几何投影 + 射线检测确认三位考官真的在画面里、没被挡住。

比看像素可靠：直接问场景图"这个头的世界坐标是多少、投影到屏幕在哪、
从相机打一条射线过去第一个撞到的是不是它自己"。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "classroom-preview.html"
OUT = ROOT / "data"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def main() -> int:
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
            ],
        )
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(HTML.as_uri(), wait_until="load")
        page.wait_for_function("() => window.__sceneReady === true", timeout=25000)

        names = page.evaluate("() => window.__debug.viewNames")
        print(f"[views] {names}")

        ok = True
        # 只看"考生席"和"考官特写"两个机位
        for index, label in ((0, "考生席"), (1, "考官特写")):
            page.evaluate("(i) => window.__debug.setView(i)", index)
            page.wait_for_timeout(400)
            heads = page.evaluate("() => window.__debug.inspectHeads()")
            print(f"\n[{label}]")
            for h in heads:
                if "error" in h:
                    print(f"  !! {h['name']}: {h['error']}")
                    ok = False
                    continue
                hit = h["firstHit"]
                owner = hit["owner"] if hit else "无"
                self_hit = owner == f"person:{h['name']}"
                mark = "OK " if (h["inFrame"] and self_hit) else "!! "
                if not (h["inFrame"] and self_hit):
                    ok = False
                print(
                    f"  {mark}{h['name']}  世界{h['world']}  NDC{h['ndc']}  "
                    f"距离{h['headDist']}m  第一命中={owner}({hit['dist'] if hit else '-'})"
                )

        # 顺手拍一张脸部特写，供人工确认
        page.evaluate("() => window.__debug.setView(2)")
        page.wait_for_timeout(700)
        shot = OUT / "classroom-face.png"
        page.screenshot(path=str(shot))
        print(f"\n[shot] 脸部特写 -> {shot.name}")

        browser.close()

    if errors:
        print("\n!! 页面报错：")
        for line in errors[:6]:
            print(f"   - {line[:200]}")
        ok = False

    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
