"""探测 DeepSeek 可用模型与是否支持视觉输入。

用法：python tools/probe_deepseek.py
"""
from __future__ import annotations

import base64
import io
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

KEY = os.environ["DEEPSEEK_KEY"]
BASES = ["https://api.deepseek.com", "https://api.deepseek.com/v1"]
LINES: list[str] = []


def call(base: str, path: str, payload: dict | None = None, timeout: int = 60):
    url = base + path
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        return "ERR", f"{type(exc).__name__}: {exc}"


def font(size: int):
    for p in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def sample_image() -> bytes:
    img = Image.new("RGB", (520, 160), "white")
    d = ImageDraw.Draw(img)
    d.text((20, 20), "星期一 08:00-09:40 高等数学 A101 张教授", fill="black", font=font(18))
    d.text((20, 70), "星期二 10:00-11:40 大学英语 C305 王老师", fill="black", font=font(18))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def main() -> int:
    for base in BASES:
        status, body = call(base, "/models")
        LINES.append(f"=== GET {base}/models -> {status}")
        if status == 200:
            try:
                ids = [m.get("id") for m in json.loads(body).get("data", [])]
                LINES.append("models: " + ", ".join(str(i) for i in ids))
            except Exception:
                LINES.append(body[:500])
        else:
            LINES.append(body[:400])

    b64 = base64.b64encode(sample_image()).decode()

    # 纯文本探测：确认模型名是否存在
    for model in ["deepseek-flash", "deepseek-chat", "deepseek-reasoner"]:
        status, body = call(
            "https://api.deepseek.com", "/chat/completions",
            {"model": model, "messages": [{"role": "user", "content": "回复：ok"}], "max_tokens": 10},
        )
        LINES.append(f"=== TEXT {model} -> {status}  {body[:300]}")

    # 视觉探测：deepseek-chat 是否接受 image_url
    status, body = call(
        "https://api.deepseek.com", "/chat/completions",
        {
            "model": "deepseek-chat",
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": "读出图中的课程行，原样输出。"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}},
                ],
            }],
            "max_tokens": 300,
        },
    )
    LINES.append(f"=== VISION deepseek-chat -> {status}")
    LINES.append(body[:900])

    report = "\n".join(LINES)
    print(report)
    Path("tools/deepseek_probe.txt").write_text(report + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
