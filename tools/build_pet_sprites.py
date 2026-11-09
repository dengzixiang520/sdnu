"""把「大肥鱼」动画从黑底视频转成带透明通道的动画 WebP。

为什么不用 ffmpeg 的 colorkey/chromakey：
    VP9 压缩会在背景产生块效应，部分背景像素的亮度或色度超出容差，
    colorkey 会漏抠成一块块残留（用户看到的"发白"）；容差调大又会把
    角色的深色部分一起吃掉。

这里的方案是按「连通性」判定背景：
    背景一定与图像四边相连，角色内部的深色像素不连通到边界。
    用 OpenCV 对「暗色掩膜」做泛洪填充，凡是能从边界走到的暗色像素都是背景，
    走不到的就是角色。再对角色边缘做一次抗锯齿，保留少量真实半透明像素。

用法：
    python tools/build_pet_sprites.py <素材目录> <输出目录>
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

# 选取的动画：原始 id -> 输出名（按暖心引导员的角色状态命名）
PICK: list[tuple[str, str]] = [
    ("anim-058", "idle-breath"),  # 待机呼吸休闲
    ("anim-003", "idle-look"),    # 东张西望
    ("anim-061", "sleep"),        # 打瞌睡被惊醒
    ("anim-078", "wave"),         # 点击回应-元气挥手
    ("anim-080", "cheer"),        # 点击回应-开心跃动
    ("anim-081", "shy"),          # 点击回应-挠痒咯咯笑
    ("anim-077", "pout"),         # 点击回应-傲娇生气
    ("anim-055", "thinking"),     # 工作状态-思考冒泡
    ("anim-087", "talking"),      # 碎碎念-对屏碎碎念
    ("anim-098", "dragged"),      # 被鼠标拖拽悬空反馈
    ("anim-046", "yawn"),         # 哈欠连天
    ("anim-012", "snack"),        # 偷吃零食被抓住
    ("anim-037", "milktea"),      # 吃糖葫芦
]

CROP = (180, 28, 290, 312)  # x, y, w, h —— 覆盖全部 13 段动画的角色范围
FPS = 9
FRAME_STEP = 2  # 原视频 24fps，每 2 帧取 1 帧，输出约 12fps 且体积减半
QUALITY = 68
DARK_LUM = 46          # 亮度低于此视为「可能是背景」
ERODE_EDGES = 1        # 角色掩膜腐蚀半径，避免把背景噪点带进来


def key_out_background(bgr: np.ndarray) -> np.ndarray:
    """从 BGR 帧生成 RGBA；背景 = 与图像边界连通的暗色区域。"""
    lum = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    dark = (lum < DARK_LUM).astype(np.uint8)

    # 只保留与边界连通的暗色区域作为背景候选
    mask = np.zeros((dark.shape[0] + 2, dark.shape[1] + 2), np.uint8)
    flood = dark.copy()
    h, w = dark.shape
    for x in range(w):
        for y in (0, h - 1):
            if flood[y, x] and not mask[y + 1, x + 1]:
                cv2.floodFill(flood, mask, (x, y), 2)
    for y in range(h):
        for x in (0, w - 1):
            if flood[y, x] and not mask[y + 1, x + 1]:
                cv2.floodFill(flood, mask, (x, y), 2)
    background = (flood == 2)

    character = (~background).astype(np.uint8)
    if ERODE_EDGES:
        kernel = np.ones((ERODE_EDGES * 2 + 1, ERODE_EDGES * 2 + 1), np.uint8)
        character = cv2.erode(character, kernel, iterations=1)

    # 抗锯齿：把角色边缘向外扩一圈，按与背景的距离给部分透明
    alpha = (character * 255).astype(np.uint8)
    soft = cv2.GaussianBlur(alpha, (3, 3), 0)
    alpha = np.maximum(alpha, (soft * 0.45).astype(np.uint8))

    rgba = np.dstack([cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), alpha])
    # 背景像素的 RGB 清零，避免编码器把残留色值扩散成白雾
    rgba[alpha == 0, :3] = 0
    return rgba


def build(source_dir: Path, output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    x, y, w, h = CROP
    total_bytes = 0

    for anim_id, name in PICK:
        source = source_dir / f"{anim_id}.webm"
        capture = cv2.VideoCapture(str(source))
        if not capture.isOpened():
            print(f"[跳过] 打不开 {source.name}")
            continue

        frames: list[Image.Image] = []
        index = 0
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if index % FRAME_STEP == 0:
                cropped = frame[y:y + h, x:x + w]
                frames.append(Image.fromarray(key_out_background(cropped), mode="RGBA"))
            index += 1
        capture.release()
        if not frames:
            print(f"[跳过] {source.name} 没解出帧")
            continue

        target = output_dir / f"{name}.webp"
        duration = max(1, round(1000 / FPS))
        frames[0].save(
            target,
            save_all=True,
            append_images=frames[1:],
            duration=duration,
            loop=0,
            format="WEBP",
            quality=QUALITY,
            method=4,
        )
        size_kb = target.stat().st_size // 1024
        total_bytes += size_kb
        print(f"[完成] {name:12} {len(frames):3} 帧  {size_kb:5} KB")

    print(f"\n合计 {len(PICK)} 段，{total_bytes // 1024} MB")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("用法: python tools/build_pet_sprites.py <素材目录> <输出目录>")
        return 2
    return build(Path(argv[1]), Path(argv[2]))


if __name__ == "__main__":
    sys.exit(main(sys.argv))

