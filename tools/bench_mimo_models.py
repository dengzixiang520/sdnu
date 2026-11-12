"""对比 mimo-v2.6-pro 与 mimo-v2.6-flash 在真实课表图上的速度与准确率。

用法：python tools/bench_mimo_models.py
需要 PYTHONPATH 指向 src。
"""
from __future__ import annotations

import asyncio
import io
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path("src").resolve()))

from zhihui_qilu.api.routes.timetable import parse_image_timetable  # noqa: E402
from zhihui_qilu.config import get_settings  # noqa: E402

MODELS = ["mimo-v2.6-pro", "mimo-v2.6-flash"]
ROUNDS = 2


def font(size: int):
    for path in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
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


async def main() -> int:
    settings = get_settings()
    if settings.mimo_api_key is None:
        print("ZHQ_MIMO_API_KEY 未配置")
        return 1

    images = {"表格A": table_layout(), "网格B": grid_layout()}
    lines: list[str] = []
    summary: dict[str, list[tuple[float, int, int]]] = {m: [] for m in MODELS}

    for model in MODELS:
        settings.mimo_model = model  # get_settings() 是 lru_cache，直接改实例即可
        for layout, data in images.items():
            for round_index in range(ROUNDS):
                started = time.perf_counter()
                try:
                    events = await parse_image_timetable(data)
                    elapsed = time.perf_counter() - started
                    got = signature(events)
                    want = EXPECTED[layout]
                    hit = len(got & want)
                    summary[model].append((elapsed, hit, len(want)))
                    lines.append(
                        f"{model:20s} {layout} 第{round_index + 1}次  {elapsed:6.2f}s  "
                        f"命中 {hit}/{len(want)}  多出 {len(got - want)}  缺失 {len(want - got)}"
                    )
                    for extra in sorted(got - want):
                        lines.append(f"    多余: {extra}")
                    for missing in sorted(want - got):
                        lines.append(f"    缺失: {missing}")
                except Exception as exc:  # noqa: BLE001 - 诊断脚本
                    elapsed = time.perf_counter() - started
                    summary[model].append((elapsed, 0, len(EXPECTED[layout])))
                    lines.append(f"{model:20s} {layout} 第{round_index + 1}次  {elapsed:6.2f}s  EXCEPTION {type(exc).__name__}: {exc}")

    lines.append("")
    lines.append("===== 汇总 =====")
    for model in MODELS:
        rows = summary[model]
        if not rows:
            continue
        avg_time = sum(r[0] for r in rows) / len(rows)
        avg_acc = sum(r[1] for r in rows) / sum(r[2] for r in rows) * 100
        lines.append(f"{model:20s} 平均 {avg_time:6.2f}s   准确率 {avg_acc:5.1f}%   调用 {len(rows)} 次")

    report = "\n".join(lines)
    print(report)
    Path("tools/mimo_bench.txt").write_text(report + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
