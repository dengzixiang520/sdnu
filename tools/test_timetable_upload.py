"""端到端验证 /api/v1/timetable/upload 的截图识别（真实 HTTP）。

用法：python tools/test_timetable_upload.py
"""
from __future__ import annotations

import io
import json
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE = "http://127.0.0.1:8000"
USER = "demo-student"
SESSION = str(uuid.uuid4())


def font(size: int):
    for path in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def grid_layout() -> bytes:
    days = ["星期一", "星期二", "星期三", "星期四", "星期五"]
    slots = [
        ("第1-2节\n08:20-09:55", ["高等数学\nA101 张教授", "", "大学英语\nC305 王老师", "", ""]),
        ("第3-4节\n10:10-11:45", ["", "数据结构\nB202 李老师", "", "", "线性代数\nA203 孙老师"]),
        ("第5-6节\n14:00-15:35", ["", "", "", "计算机网络\nE105 周老师", ""]),
    ]
    width, height = 1000, 420
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    head, body = font(18), font(16)
    col0, colw, rowh, top = 150, 170, 118, 56
    draw.rectangle([0, 0, width - 1, top - 1], fill="#e8eef0")
    draw.text((12, 18), "节次/星期", fill="black", font=head)
    for i, day in enumerate(days):
        draw.text((col0 + i * colw + 40, 18), day, fill="black", font=head)
    for r, (slot, cells) in enumerate(slots):
        y = top + r * rowh
        draw.line([0, y, width, y], fill="#cccccc")
        draw.multiline_text((12, y + 30), slot, fill="black", font=body)
        for c, cell in enumerate(cells):
            x = col0 + c * colw
            draw.rectangle([x, y, x + colw, y + rowh], outline="#dddddd")
            if cell:
                draw.multiline_text((x + 12, y + 34), cell, fill="black", font=body)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def post_file(image_bytes: bytes, filename: str) -> tuple[int, str]:
    boundary = "----zhq" + uuid.uuid4().hex
    parts = [
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
        b"Content-Type: image/png\r\n\r\n",
        image_bytes,
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    body = b"".join(parts)
    req = urllib.request.Request(
        BASE + "/api/v1/timetable/upload",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "X-User-Id": USER,
            "X-Session-Id": SESSION,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def main() -> int:
    lines: list[str] = []
    status, raw = post_file(grid_layout(), "timetable.png")
    lines.append(f"HTTP {status}")
    try:
        data = json.loads(raw)
    except ValueError:
        lines.append("RAW: " + raw[:800])
        Path("tools/timetable_upload_result.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines))
        return 1

    lines.append(f"success={data.get('success')}  message={data.get('message')}")
    for event in data.get("events", []):
        lines.append(
            f"  {event['day_of_week']}  {event['starts_at'][11:16]}-{event['ends_at'][11:16]}"
            f"  {event['title']}  @{event['location']}  {event['teacher']}"
        )
    if not data.get("events") and "detail" in data:
        lines.append("detail: " + str(data["detail"])[:400])

    report = "\n".join(lines)
    print(report)
    Path("tools/timetable_upload_result.txt").write_text(report + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
