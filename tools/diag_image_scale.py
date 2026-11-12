"""测试图片缩放对推理量与延迟的影响。

用法：python tools/diag_image_scale.py tools/user_timetable.jpg
"""
from __future__ import annotations

import asyncio
import base64
import io
import sys
import time
from pathlib import Path

import httpx
from PIL import Image

sys.path.insert(0, str(Path("src").resolve()))

from zhihui_qilu.api.routes.timetable import VISION_PROMPT  # noqa: E402
from zhihui_qilu.config import get_settings  # noqa: E402


def load_key() -> str:
    for line in Path(".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("ZHQ_DEEPSEEK_VISION_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("找不到 key")


def scaled(data: bytes, max_side: int) -> bytes:
    image = Image.open(io.BytesIO(data)).convert("RGB")
    width, height = image.size
    longest = max(width, height)
    if longest <= max_side:
        return data
    ratio = max_side / longest
    image = image.resize((max(1, int(width * ratio)), max(1, int(height * ratio))), Image.LANCZOS)
    buf = io.BytesIO()
    image.save(buf, "JPEG", quality=85)
    return buf.getvalue()


async def run(client: httpx.AsyncClient, key: str, label: str, data: bytes, lines: list[str]) -> None:
    payload = {
        "model": "deepseek-flash",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": VISION_PROMPT},
                {"type": "image_url", "image_url": {
                    "url": "data:image/jpeg;base64," + base64.b64encode(data).decode()
                }},
            ],
        }],
        "max_tokens": 16000,
        "temperature": 0,
        "effort": "low",
    }
    started = time.perf_counter()
    try:
        response = await client.post(
            "https://api.deepseek.com/chat/completions",
            json=payload,
            headers={"Authorization": "Bearer " + key},
        )
        elapsed = time.perf_counter() - started
        body = response.json()
        choice = body["choices"][0]
        usage = body.get("usage", {})
        reasoning = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
        content = (choice["message"].get("content") or "").strip()
        lines.append(
            f"{label:22s} {len(data) // 1024:4d}KB  {elapsed:6.2f}s  finish={choice.get('finish_reason'):7s} "
            f"prompt={usage.get('prompt_tokens'):5d} reasoning={str(reasoning):5s} "
            f"content_len={len(content):4d}"
        )
    except Exception as exc:  # noqa: BLE001
        lines.append(f"{label:22s} EXCEPTION {type(exc).__name__}: {str(exc)[:100]}")


async def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "tools/user_timetable.jpg")
    raw = path.read_bytes()
    key = load_key()
    settings = get_settings()
    lines = [f"原图 {path}  {len(raw)} bytes  {Image.open(io.BytesIO(raw)).size}"]
    lines.append(f"prompt 长度 {len(VISION_PROMPT)} 字符")
    lines.append("")

    variants = [
        ("原图 1080x2400", raw),
        ("max_side=1400", scaled(raw, 1400)),
        ("max_side=1100", scaled(raw, 1100)),
        ("max_side=800", scaled(raw, 800)),
    ]

    async with httpx.AsyncClient(timeout=300.0) as client:
        for label, data in variants:
            await run(client, key, label, data, lines)

    report = "\n".join(lines)
    print(report)
    Path("tools/image_scale_diag.txt").write_text(report + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
