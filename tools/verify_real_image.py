"""用真实截图验证 /api/v1/timetable/upload。

用法：python tools/verify_real_image.py [图片路径]
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

BASE = "http://127.0.0.1:8000"
PATH = Path(sys.argv[1] if len(sys.argv) > 1 else "tools/user_timetable.jpg")
USER = "demo-student"
SESSION = str(uuid.uuid4())

MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


def main() -> int:
    data = PATH.read_bytes()
    boundary = "----zhq" + uuid.uuid4().hex
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{PATH.name}"\r\n'.encode(),
        f"Content-Type: {MIME.get(PATH.suffix.lower(), 'image/jpeg')}\r\n\r\n".encode(),
        data,
        f"\r\n--{boundary}--\r\n".encode(),
    ])
    request = urllib.request.Request(
        BASE + "/api/v1/timetable/upload",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "X-User-Id": USER,
            "X-Session-Id": SESSION,
        },
        method="POST",
    )

    lines = [f"图片 {PATH}  {len(data)} bytes"]
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            status, raw = response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        status, raw = exc.code, exc.read().decode("utf-8", "replace")
    elapsed = time.perf_counter() - started

    lines.append(f"HTTP {status}  耗时 {elapsed:.2f}s")
    try:
        payload = json.loads(raw)
    except ValueError:
        lines.append("RAW: " + raw[:800])
        report = "\n".join(lines)
        print(report)
        Path("tools/real_image_result.txt").write_text(report + "\n", encoding="utf-8")
        return 1

    if "detail" in payload:
        lines.append("detail: " + str(payload["detail"]))

    events = payload.get("events") or []
    lines.append(f"success={payload.get('success')}  message={payload.get('message')}  课程数={len(events)}")
    for event in events:
        lines.append(
            f"  {event['day_of_week']}  {event['starts_at'][11:16]}-{event['ends_at'][11:16]}"
            f"  {event['title']}  @{event['location']}  {event['teacher']}"
        )

    report = "\n".join(lines)
    print(report)
    Path("tools/real_image_result.txt").write_text(report + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
