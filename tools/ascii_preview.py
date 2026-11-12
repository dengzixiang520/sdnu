"""把渲染图降采样成字符画，用来在"看不了图片"的情况下检查构图。

每个格子取平均色再归类：
  S 肤色   K 深色(头发/瞳孔)   B 黑板绿   R 红   W 浅色(墙/衬衫)   M 木色/暖色   . 其他
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

OUT = Path(__file__).resolve().parent.parent / "data"
COLS, ROWS = 72, 30


def classify(r: float, g: float, b: float) -> str:
    if r < 78 and g < 78 and b < 78:
        return "K"
    if g > r + 10 and g > b + 4 and g < 145:
        return "B"
    if r > 140 and r > g + 60 and r > b + 65:
        return "R"
    if r > 176 and 12 < r - g < 60 and 14 < g - b < 54 and b > 100 and r > b + 36:
        return "S"
    if r > 196 and g > 190 and b > 178:
        return "W"
    if r > b + 22:
        return "M"
    return "."


def render(name: str, label: str) -> dict[str, float]:
    img = Image.open(OUT / name).convert("RGB")
    small = img.resize((COLS, ROWS), Image.BILINEAR)
    px = list(small.getdata())

    counts: dict[str, int] = {}
    print(f"\n=== {label} · {name} ===")
    for row in range(ROWS):
        line = []
        for col in range(COLS):
            r, g, b = px[row * COLS + col]
            ch = classify(r, g, b)
            counts[ch] = counts.get(ch, 0) + 1
            line.append(ch)
        print("  " + "".join(line))

    total = COLS * ROWS
    pct = {k: v / total * 100 for k, v in counts.items()}
    print("  占比: " + "  ".join(f"{k} {pct[k]:.1f}%" for k in sorted(pct, key=lambda x: -pct[x])))
    return pct


def main() -> int:
    a = render("classroom-3-脸部特写.png", "脸部特写")
    b = render("classroom-1-考生席.png", "考生席")

    ok = True
    if a.get("S", 0) < 8:
        print("\n!! 特写里肤色太少，人物可能没渲染出来")
        ok = False
    if a.get("K", 0) < 0.4:
        print("\n!! 特写里几乎没有深色（头发/瞳孔），面部细节可能没出来")
        ok = False
    if b.get("B", 0) < 1:
        print("\n!! 考生席视角看不到黑板绿，机位可能不对")
        ok = False

    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
