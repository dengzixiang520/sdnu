"""检查预览截图的像素分布，确认画面不是全黑 / 全白，并且关键元素都在。

因为当前模型看不了图片，只能靠色彩统计间接确认渲染结果：
黑板应该是暗绿、横幅应该是红、地面应该是米色。
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

OUT = Path(__file__).resolve().parent.parent / "data"

SHOTS = [
    ("考生席", "classroom-1-考生席.png"),
    ("讲台", "classroom-2-讲台.png"),
    ("侧墙", "classroom-3-侧墙.png"),
    ("全景", "classroom-4-全景.png"),
]


def classify(r: int, g: int, b: int) -> str:
    sat = max(r, g, b) - min(r, g, b)
    if g > r + 12 and g > b + 8 and g < 130:
        return "board"
    if r > 135 and r > g + 65 and r > b + 70:
        return "red"
    if r > 80 and r - b > 40 and 22 < r - g < 72 and b < 110:
        return "wood"
    if r > 185 and g > 180 and b > 170 and sat < 36:
        return "light"
    if r < 45 and g < 45 and b < 45:
        return "dark"
    return "other"


def main() -> int:
    ok = True
    for label, name in SHOTS:
        path = OUT / name
        if not path.exists():
            print(f"!! 缺图 {name}")
            ok = False
            continue

        img = Image.open(path).convert("RGB")
        img = img.resize((320, 180))
        pixels = list(img.getdata())
        total = len(pixels)

        buckets = {"board": 0, "red": 0, "wood": 0, "light": 0, "dark": 0, "other": 0}
        sr = sg = sb = 0
        for r, g, b in pixels:
            buckets[classify(r, g, b)] += 1
            sr += r
            sg += g
            sb += b

        mean = (sr / total, sg / total, sb / total)
        pct = {k: v / total * 100 for k, v in buckets.items()}

        print(f"\n[{label}] {name}")
        print(f"  平均色  R{mean[0]:.0f} G{mean[1]:.0f} B{mean[2]:.0f}")
        print(
            "  占比    "
            f"黑板绿 {pct['board']:.1f}%  红 {pct['red']:.1f}%  "
            f"木色 {pct['wood']:.1f}%  浅色 {pct['light']:.1f}%  暗 {pct['dark']:.1f}%"
        )

        if mean[0] < 12 and mean[1] < 12 and mean[2] < 12:
            print("  !! 画面几乎全黑")
            ok = False
        if pct["dark"] > 92:
            print("  !! 92% 以上是暗部，场景大概没渲染出来")
            ok = False

    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
