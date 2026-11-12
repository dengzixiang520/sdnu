"""用用户真实截图诊断 DeepSeek 视觉调用为何返回空 content。

用法：python tools/diag_vision_budget.py tools/user_timetable.jpg
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path("src").resolve()))

from zhihui_qilu.api.routes.timetable import VISION_PROMPT  # noqa: E402


def load_key() -> str:
    key = os.environ.get("DEEPSEEK_KEY")
    if key:
        return key
    for line in Path(".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("ZHQ_DEEPSEEK_VISION_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("找不到 DeepSeek key")


async def probe(
    client: httpx.AsyncClient,
    key: str,
    image: bytes,
    effort: str | None,
    max_tokens: int,
    lines: list[str],
) -> None:
    payload = {
        "model": "deepseek-flash",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": VISION_PROMPT},
                {"type": "image_url", "image_url": {
                    "url": "data:image/jpeg;base64," + base64.b64encode(image).decode()
                }},
            ],
        }],
        "max_tokens": max_tokens,
        "temperature": 0,
    }
    if effort:
        payload["effort"] = effort

    started = time.perf_counter()
    try:
        response = await client.post(
            "https://api.deepseek.com/chat/completions",
            json=payload,
            headers={"Authorization": "Bearer " + key},
        )
    except Exception as exc:  # noqa: BLE001
        lines.append(f"effort={effort} max={max_tokens}  EXCEPTION {type(exc).__name__}: {exc}")
        return
    elapsed = time.perf_counter() - started

    if response.status_code >= 400:
        lines.append(f"effort={effort} max={max_tokens}  HTTP {response.status_code} {response.text[:200]}")
        return

    body = response.json()
    choice = body["choices"][0]
    message = choice["message"]
    usage = body.get("usage", {})
    reasoning = usage.get("completion_tokens_details", {}).get("reasoning_tokens")
    content = (message.get("content") or "").strip()
    lines.append(
        f"effort={str(effort):5s} max={max_tokens:6d}  {elapsed:6.2f}s  "
        f"finish={choice.get('finish_reason'):8s} content_len={len(content):5d}  "
        f"prompt={usage.get('prompt_tokens')} completion={usage.get('completion_tokens')} "
        f"reasoning={reasoning}"
    )
    if content:
        preview = content[:300].replace("\n", " ")
        lines.append(f"    content: {preview}")


async def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "tools/user_timetable.jpg")
    image = path.read_bytes()
    key = load_key()
    lines = [f"图片 {path}  {len(image)} bytes"]
    lines.append("")

    async with httpx.AsyncClient(timeout=300.0) as client:
        for effort in ["low", "high", None]:
            for max_tokens in [2500, 8000, 16000]:
                await probe(client, key, image, effort, max_tokens, lines)

    report = "\n".join(lines)
    print(report)
    Path("tools/vision_budget_diag.txt").write_text(report + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
