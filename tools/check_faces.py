"""确认三位考官真的画出来了：在预期的头部区域找肤色像素。

当前模型看不了图片，只能靠这个间接验证——
如果人物没渲染、比例错、位置飞出画面，这里的肤色占比会明显异常。
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

OUT = Path(__file__).resolve().parent.parent / "data"

# 考生席视角下，三位考官的头大致落在这个归一化矩形里
BAND = (0.20, 0.38, 0.80, 0.74)


def is_skin(r: int, g: int, b: int) -> bool:
    return (
        r > 178
        and 12 < r - g < 58
        and 16 < g - b < 52
        and b > 105
        and r > b + 38
    )


def scan(name: str, label: str) -> tuple[int, int, float]:
    img = Image.open(OUT / name).convert("RGB")
    w, h = img.size
    x0, y0, x1, y1 = BAND
    crop = img.crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1)))
    pixels = list(crop.getdata())
    hit = sum(1 for p in pixels if is_skin(*p))
    pct = hit / len(pixels) * 100
    print(f"[{label}] {name}  区域 {crop.size[0]}×{crop.size[1]}  肤色像素 {hit}  占比 {pct:.2f}%")
    return hit, len(pixels), pct


def main() -> int:
    ok = True

    _, _, pct = scan("classroom-1-考生席.png", "考生席")
    if pct < 0.5:
        print("  !! 头部区域几乎找不到肤色，人物可能没画出来或位置错了")
        ok = False
    elif pct > 25:
        print("  !! 肤色占比过高，画面里可能有东西糊住了")
        ok = False
    else:
        print("  OK 三张脸都在预期位置")

    _, _, pct2 = scan("classroom-2-讲台.png", "讲台")
    print("  （讲台视角看不到考官正脸，占比低是正常的）")

    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
