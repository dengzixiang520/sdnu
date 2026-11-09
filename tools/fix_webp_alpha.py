"""把动画 WebP 的 alpha 通道修正为"主体钉死、边缘保留渐变"。

为什么需要这一步：
    ffmpeg 的 libwebp_anim 编码器没有暴露 alpha_quality 参数，有损编码会把
    alpha 通道一起做 DCT 量化。结果是角色主体（本应完全不透明）的 alpha 掉到
    248-254，浏览器与页面背景混合后整个角色发灰、像蒙了一层白光。

处理方式：
    逐帧解码 -> 按 alpha 分三段映射 -> 重新编码为动画 WebP。
      a >= SOLID_MIN  -> 255   （主体，钉死不透明）
      a <= CLEAR_MAX  -> 0     （纯背景，彻底透明）
      中间            -> 原值  （真实边缘抗锯齿，保留）

用法：
    python tools/fix_webp_alpha.py web/public/pet
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

SOLID_MIN = 250
CLEAR_MAX = 6
FPS = 9
QUALITY = 72


def repair(path: Path) -> tuple[int, int, int]:
    """Repair one animated WebP in place; returns (frames, semi_before, semi_after)."""
    image = Image.open(path)
    frames: list[Image.Image] = []
    semi_before = 0
    for index in range(getattr(image, "n_frames", 1)):
        image.seek(index)
        frame = np.array(image.convert("RGBA"), dtype=np.uint8)
        alpha = frame[:, :, 3]
        semi_before += int(np.count_nonzero((alpha > CLEAR_MAX) & (alpha < SOLID_MIN)))

        # 三段映射：主体钉 255，背景清 0，边缘保留
        solid = alpha >= SOLID_MIN
        clear = alpha <= CLEAR_MAX
        frame[:, :, 3][solid] = 255
        frame[:, :, 3][clear] = 0
        # 完全透明像素的 RGB 也清零，避免编码器把残留色值扩散成白雾
        frame[:, :, :3][clear] = 0
        frames.append(Image.fromarray(frame, mode="RGBA"))

    duration = max(1, round(1000 / FPS))
    frames[0].save(
        path,
        save_all=True,
        append_images=frames[1:],
        duration=duration,
        loop=0,
        format="WEBP",
        quality=QUALITY,
        method=6,
    )

    check = Image.open(path)
    check.seek(0)
    alpha = np.array(check.convert("RGBA"), dtype=np.uint8)[:, :, 3]
    semi_after = int(np.count_nonzero((alpha > CLEAR_MAX) & (alpha < SOLID_MIN)))
    return len(frames), semi_before, semi_after


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("用法: python tools/fix_webp_alpha.py <目录>")
        return 2
    target = Path(argv[1])
    files = sorted(target.glob("*.webp"))
    if not files:
        print(f"[错误] {target} 下没有 .webp")
        return 1

    total_before = total_after = 0
    for path in files:
        frames, before, after = repair(path)
        total_before += before
        total_after += after
        print(f"[修复] {path.name:18} {frames:3} 帧  半透明 {before:6} -> {after:5}  {path.stat().st_size // 1024} KB")

    print()
    print(f"合计半透明边缘像素：{total_before} -> {total_after}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
