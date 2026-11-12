"""三方速度/准确率对比：mimo-v2.6-pro / mimo-v2.6-flash / deepseek-flash。

同一张图、同一套生产提示词（VISION_PROMPT）、同样 max_tokens 与 temperature。
用法：python tools/bench_three_models.py
需要 PYTHONPATH 指向 src，并设置 MIMO_KEY / DEEPSEEK_KEY。
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import sys
import time
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path("src").resolve()))

from zhihui_qilu.api.routes.timetable import (  # noqa: E402
    VISION_PROMPT,
    _events_from_rows,
    _extract_json_array,
)

ROUNDS = 3
MAX_TOKENS = 2500
RETRIES = 4

# (显示名, base_url, model, 环境变量名, 额外请求参数)
PROVIDERS = [
    ("mimo-v2.6-pro", "https://api.xiaomimimo.com/v1", "mimo-v2.6-pro", "MIMO_KEY", {}),
    ("mimo-v2.6-flash", "https://api.xiaomimimo.com/v1", "mimo-v2.6-flash", "MIMO_KEY", {}),
    ("deepseek-flash", "https://api.deepseek.com", "deepseek-flash", "DEEPSEEK_KEY", {}),
    ("deepseek-flash/effort=low", "https://api.deepseek.com", "deepseek-flash", "DEEPSEEK_KEY",
     {"effort": "low"}),
]


def font(size: int):
    for p in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def table_layout() -> bytes:
    rows = [
        ("星期一", "08:00-09:40", "高等数学", "A101", "张教授"),
        ("星期二", "10:00-11:40", "大学英语", "C305", "王老师"),
        ("星期三", "14:00-15:40", "数据结构", "B202", "李老师"),
        ("星期四", "19:00-20:35", "Python程序设计", "D401", "赵教授"),
    ]
    img = Image.new("RGB", (860, 340), "white")
    draw = ImageDraw.Draw(img)
    head, body = font(20), font(19)
    draw.rectangle([0, 0, 859, 48], fill="#e8eef0")
    for i, title in enumerate(["星期", "时间", "课程", "地点", "教师"]):
        draw.text((22 + i * 165, 14), title, fill="black", font=head)
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            draw.text((22 + c * 165, 74 + r * 66), value, fill="black", font=body)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


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


EXPECTED = {
    "表格A": {
        ("周一", "08:00", "高等数学", "A101", "张教授"),
        ("周二", "10:00", "大学英语", "C305", "王老师"),
        ("周三", "14:00", "数据结构", "B202", "李老师"),
        ("周四", "19:00", "Python程序设计", "D401", "赵教授"),
    },
    "网格B": {
        ("周一", "08:20", "高等数学", "A101", "张教授"),
        ("周三", "08:20", "大学英语", "C305", "王老师"),
        ("周二", "10:10", "数据结构", "B202", "李老师"),
        ("周五", "10:10", "线性代数", "A203", "孙老师"),
        ("周四", "14:00", "计算机网络", "E105", "周老师"),
    },
}


def signature(events: list[dict[str, str]]) -> set[tuple[str, str, str, str, str]]:
    return {
        (e["day_of_week"], e["starts_at"][11:16], e["title"], e["location"], e["teacher"])
        for e in events
    }


async def ask(
    client: httpx.AsyncClient,
    base: str,
    model: str,
    key: str,
    image: bytes,
    extra: dict | None = None,
):
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": VISION_PROMPT},
                {"type": "image_url", "image_url": {
                    "url": "data:image/png;base64," + base64.b64encode(image).decode()
                }},
            ],
        }],
        "max_tokens": MAX_TOKENS,
        "temperature": 0,
    }
    if extra:
        payload.update(extra)

    # 这台机器到两个 API 的 DNS 会瞬时失败，单次请求不足以下结论。
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            started = time.perf_counter()
            response = await client.post(
                base.rstrip("/") + "/chat/completions",
                json=payload,
                headers={"Authorization": "Bearer " + key},
            )
            elapsed = time.perf_counter() - started
            response.raise_for_status()
            body = response.json()
            message = body["choices"][0]["message"]
            return elapsed, (message.get("content") or ""), body.get("usage", {})
        except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError,
                httpx.ReadTimeout, httpx.ConnectTimeout) as exc:
            last = exc
            await asyncio.sleep(1.2 * (attempt + 1))
    raise last if last else RuntimeError("unknown failure")


async def main() -> int:
    keys = {name: os.environ.get(env) for _, _, _, env, _ in PROVIDERS for name in [env]}
    missing = [env for env, value in keys.items() if not value]
    if missing:
        print("缺少环境变量: " + ", ".join(missing))
        return 1

    images = {"表格A": table_layout(), "网格B": grid_layout()}
    lines: list[str] = []
    stats: dict[str, list[tuple[float, int, int]]] = {p[0]: [] for p in PROVIDERS}

    async with httpx.AsyncClient(timeout=180.0) as client:
        for label, base, model, env, extra in PROVIDERS:
            key = keys[env]
            for layout, data in images.items():
                for round_index in range(ROUNDS):
                    try:
                        elapsed, content, usage = await ask(client, base, model, key, data, extra)
                    except Exception as exc:  # noqa: BLE001 - 诊断脚本
                        stats[label].append((0.0, 0, len(EXPECTED[layout])))
                        lines.append(
                            f"{label:18s} {layout} 第{round_index + 1}次  "
                            f"EXCEPTION {type(exc).__name__}: {str(exc)[:120]}"
                        )
                        continue
                    rows = _extract_json_array(content)
                    events = _events_from_rows(rows) if rows else []
                    got, want = signature(events), EXPECTED[layout]
                    hit = len(got & want)
                    stats[label].append((elapsed, hit, len(want)))
                    reasoning = usage.get("completion_tokens_details", {}).get("reasoning_tokens")
                    lines.append(
                        f"{label:18s} {layout} 第{round_index + 1}次  {elapsed:6.2f}s  "
                        f"命中 {hit}/{len(want)}  多出 {len(got - want)}  缺失 {len(want - got)}  "
                        f"tokens={usage.get('total_tokens')} reasoning={reasoning}"
                    )

    lines.append("")
    lines.append("===== 汇总（仅统计成功调用） =====")
    ranking = []
    for label, _, _, _, _ in PROVIDERS:
        rows = [r for r in stats[label] if r[0] > 0]
        if not rows:
            lines.append(f"{label:18s} 全部失败")
            continue
        times = sorted(r[0] for r in rows)
        avg = sum(times) / len(times)
        median = times[len(times) // 2]
        accuracy = sum(r[1] for r in rows) / sum(r[2] for r in rows) * 100
        ranking.append((avg, median, accuracy, label, len(rows)))
        lines.append(
            f"{label:18s} 平均 {avg:6.2f}s  中位 {median:6.2f}s  最快 {times[0]:6.2f}s  "
            f"准确率 {accuracy:5.1f}%  成功 {len(rows)}/{ROUNDS * len(images)}"
        )

    if ranking:
        ranking.sort()
        lines.append("")
        lines.append("===== 速度排名 =====")
        for index, (avg, median, accuracy, label, count) in enumerate(ranking, 1):
            lines.append(f"  {index}. {label}  平均 {avg:.2f}s  中位 {median:.2f}s  准确率 {accuracy:.1f}%")
        lines.append("")
        lines.append(f"最快：{ranking[0][3]}")

    report = "\n".join(lines)
    print(report)
    Path("tools/bench_three.txt").write_text(report + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
