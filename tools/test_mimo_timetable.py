"""直接验证 MiMo 视觉课表识别（不经过 HTTP 服务）。

用法：python tools/test_mimo_timetable.py
需要 PYTHONPATH 指向 src。
"""
from __future__ import annotations

import asyncio
import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path("src").resolve()))

from zhihui_qilu.api.routes.timetable import parse_image_timetable  # noqa: E402

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
]


def font(size: int):
    from PIL import ImageFont

    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def table_layout() -> bytes:
    """布局 A：带“星期”列的行式表格。"""
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
    """布局 B：星期做列头的教务系统网格（真实截图形态）。"""
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


async def run(name: str, data: bytes, lines: list[str]) -> None:
    lines.append(f"===== {name}  ({len(data)} bytes) =====")
    try:
        events = await parse_image_timetable(data)
    except Exception as exc:  # noqa: BLE001 - 诊断脚本，打印一切
        lines.append(f"EXCEPTION {type(exc).__name__}: {exc}")
        return
    lines.append(f"events={len(events)}")
    for event in events:
        lines.append(
            f"  {event['day_of_week']}  {event['starts_at'][11:16]}-{event['ends_at'][11:16]}"
            f"  {event['title']}  @{event['location']}  {event['teacher']}"
        )


def main() -> int:
    lines: list[str] = []
    asyncio.run(run("布局A 行式表格", table_layout(), lines))
    asyncio.run(run("布局B 教务系统网格", grid_layout(), lines))
    report = "\n".join(lines)
    print(report)
    Path("tools/mimo_timetable_result.txt").write_text(report + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
