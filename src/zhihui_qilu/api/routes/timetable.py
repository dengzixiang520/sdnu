"""课表导入与解析路由。

本模块只负责把用户上传的课表转换成前端网格需要的形状；真正的解析规则集中在
`SLOT_TIMES` / `_slot_range` / `_normalize_day` 三个地方，避免 Excel、文本、OCR
三条路径各写一套导致口径漂移。
"""

import io
import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/timetable", tags=["timetable"])

SAVE_PATH = Path("./data/timetable.json")


class TimetableEvent(BaseModel):
    title: str
    starts_at: str
    ends_at: str
    location: str = ""
    day_of_week: str = ""
    teacher: str = ""


# 节次 → (开始, 结束)。与前端 DormitoryDesk 的 slotInfo 保持同一口径。
SLOT_TIMES: dict[str, tuple[str, str]] = {
    "1": ("08:20", "09:05"), "2": ("09:10", "09:55"),
    "3": ("10:10", "10:55"), "4": ("11:00", "11:45"),
    "5": ("14:00", "14:45"), "6": ("14:50", "15:35"),
    "7": ("15:50", "16:35"), "8": ("16:40", "17:25"),
    "9": ("19:00", "19:45"), "10": ("19:50", "20:35"),
}

# 星期别名。中文键必须先于英文键，否则 "星期一" 会被 "周" 系列误判。
DAY_ALIASES: dict[str, str] = {
    "周一": "周一", "星期一": "周一", "monday": "周一", "mon": "周一",
    "周二": "周二", "星期二": "周二", "tuesday": "周二", "tue": "周二",
    "周三": "周三", "星期三": "周三", "wednesday": "周三", "wed": "周三",
    "周四": "周四", "星期四": "周四", "thursday": "周四", "thu": "周四",
    "周五": "周五", "星期五": "周五", "friday": "周五", "fri": "周五",
    "周六": "周六", "星期六": "周六", "saturday": "周六", "sat": "周六",
    "周日": "周日", "周天": "周日", "星期日": "周日", "星期天": "周日",
    "sunday": "周日", "sun": "周日",
}

# 课表只描述“每周几的什么时刻”，网格渲染也只用到星期与时分；
# starts_at / ends_at 需要一个完整时间戳，因此统一挂在这个占位日期上。
PLACEHOLDER_DATE = "2026-09-01"

_DAY_RE = re.compile(r"(周[一二三四五六日天]|星期[一二三四五六日天])")
_RANGE_RE = re.compile(r"(\d{1,2}:\d{2})\s*[-~—至到－]\s*(\d{1,2}:\d{2})")
_SLOT_RE = re.compile(r"第?\s*(\d{1,2})\s*(?:[-~、,，]\s*(\d{1,2}))?\s*节")
_LEADING_SLOT_RE = re.compile(r"^(\d{1,2})(?=\s|$)")


def _slot_range(text: str) -> tuple[str, str, str] | None:
    """把 “1-2节”“第3节”“3” 这类节次写法解析为具体时刻，并返回被匹配的原文片段。"""
    match = _SLOT_RE.search(text)
    if match and match.group(1) in SLOT_TIMES:
        first = match.group(1)
        second = match.group(2)
        end = SLOT_TIMES[second][1] if second in SLOT_TIMES else SLOT_TIMES[first][1]
        return SLOT_TIMES[first][0], end, match.group(0)
    stripped = text.strip()
    if stripped in SLOT_TIMES:
        return SLOT_TIMES[stripped][0], SLOT_TIMES[stripped][1], stripped
    # Excel 时间列常写成纯节次数字，如 “3” 或 “3 高等数学”；要求数字后是空白或行尾，
    # 这样 “3D建模” 这类课程名不会被误判成节次。
    leading = _LEADING_SLOT_RE.match(stripped)
    if leading and leading.group(1) in SLOT_TIMES:
        slot = leading.group(1)
        return SLOT_TIMES[slot][0], SLOT_TIMES[slot][1], leading.group(0)
    return None


def _normalize_day(text: str) -> str | None:
    """把 “周一” / “星期一” / “Mon” 统一成网格使用的 “周X”。"""
    lowered = text.strip().lower()
    for alias, day in DAY_ALIASES.items():
        if alias in lowered:
            return day
    return None


def _split_fields(remainder: str) -> tuple[str, str, str]:
    """把去掉星期与时间后的剩余文本切成 课程 / 地点 / 教师。"""
    text = remainder.strip()
    if not text:
        return "", "", ""
    if "@" in text:
        left, right = text.split("@", 1)
        parts = right.split()
        return left.strip(), (parts[0] if parts else ""), (parts[1] if len(parts) > 1 else "")
    parts = text.split()
    return (
        parts[0] if parts else "",
        parts[1] if len(parts) > 1 else "",
        parts[2] if len(parts) > 2 else "",
    )


def parse_text_content(text: str) -> list[dict[str, str]]:
    """解析 “周一 08:00-09:40 高等数学 A101 张教授” 这类课表文本。

    星期与时间是可识别的前缀；其余按空白顺序取 课程 / 地点 / 教师，也支持
    “课程 @ 地点 教师”。无法识别的行直接跳过，不再用默认时刻伪造课程。
    """
    events: list[dict[str, str]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        day_match = _DAY_RE.search(line)
        if day_match is None:
            continue
        day_of_week = _normalize_day(day_match.group(1))
        if day_of_week is None:
            continue
        remainder = line[day_match.end():]

        range_match = _RANGE_RE.search(remainder)
        if range_match is not None:
            start_time, end_time = range_match.group(1), range_match.group(2)
            remainder = f"{remainder[: range_match.start()]} {remainder[range_match.end():]}"
        else:
            slot = _slot_range(remainder)
            if slot is None:
                continue
            start_time, end_time, matched = slot
            remainder = remainder.replace(matched, " ", 1)

        title, location, teacher = _split_fields(remainder)
        if not title:
            continue
        events.append({
            "title": title,
            "starts_at": f"{PLACEHOLDER_DATE}T{start_time}:00",
            "ends_at": f"{PLACEHOLDER_DATE}T{end_time}:00",
            "location": location,
            "day_of_week": day_of_week,
            "teacher": teacher,
        })
    return events


def parse_pdf_timetable(pdf_bytes: bytes) -> list[dict[str, str]]:
    """PDF 课表解析尚未接入。

    仓库根目录的 `test_parse.py` 是 pdfplumber 的离线原型，但 pdfplumber 不是本项目的
    运行时依赖，也没有针对真实教务 PDF 版式的自动化测试，因此这里不返回伪数据，
    而是明确告知未支持。
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="PDF 课表解析尚未接入：请改用 Excel / CSV / 文本 / ICS 导入，或先把 PDF 转成表格文件。",
    )


def parse_ics_timetable(content_bytes: bytes) -> list[dict[str, str]]:
    """复用 dormitory_service 的 ICS 解析器，并转换成课表网格需要的形状。"""
    from zhihui_qilu.dormitory_service import TimetableParseError, TimetableParser

    try:
        text = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = content_bytes.decode("gbk", errors="replace")
    try:
        parsed = TimetableParser().parse_ics(text)
    except TimetableParseError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"ICS 解析失败：{exc}") from exc
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    return [
        {
            "title": event.title,
            "starts_at": event.starts_at.strftime("%Y-%m-%dT%H:%M:%S"),
            "ends_at": event.ends_at.strftime("%Y-%m-%dT%H:%M:%S"),
            "location": event.location or "",
            "day_of_week": weekdays[event.starts_at.weekday()],
            "teacher": "",
        }
        for event in parsed
    ]


def parse_excel_timetable(excel_bytes: bytes) -> list[dict[str, str]]:
    """解析 XLSX 的第一个可用工作表，按表头别名定位列。"""
    import openpyxl

    events: list[dict[str, str]] = []
    workbook = openpyxl.load_workbook(io.BytesIO(excel_bytes), read_only=True, data_only=True)
    try:
        for sheet in workbook.worksheets:
            rows = list(sheet.iter_rows(values_only=True))
            if not rows:
                continue
            headers = [str(cell).strip().lower() if cell is not None else "" for cell in rows[0]]
            day_col = next((i for i, h in enumerate(headers) if "星期" in h or "day" in h), None)
            time_col = next((i for i, h in enumerate(headers) if "时间" in h or "节" in h or "time" in h), None)
            name_col = next((i for i, h in enumerate(headers) if "课程" in h or "名称" in h or "name" in h), None)
            location_col = next((i for i, h in enumerate(headers) if "地点" in h or "教室" in h or "location" in h), None)
            teacher_col = next((i for i, h in enumerate(headers) if "教师" in h or "老师" in h or "teacher" in h), None)
            if day_col is None or time_col is None or name_col is None:
                continue

            for row in rows[1:]:
                if not row or not any(cell is not None for cell in row):
                    continue

                def cell(index: int | None) -> str:
                    if index is None or index >= len(row) or row[index] is None:
                        return ""
                    return str(row[index]).strip()

                name = cell(name_col)
                if not name or name == "None":
                    continue
                slot = _slot_range(cell(time_col))
                if slot is None:
                    continue
                day_of_week = _normalize_day(cell(day_col))
                if day_of_week is None:
                    continue
                start_time, end_time, _ = slot
                events.append({
                    "title": name,
                    "starts_at": f"{PLACEHOLDER_DATE}T{start_time}:00",
                    "ends_at": f"{PLACEHOLDER_DATE}T{end_time}:00",
                    "location": cell(location_col),
                    "day_of_week": day_of_week,
                    "teacher": cell(teacher_col),
                })
    finally:
        workbook.close()
    return events


def parse_image_timetable(image_bytes: bytes) -> list[dict[str, str]]:
    """调用本地 Tesseract 做 OCR，再交给文本解析器归一化。"""
    try:
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="图片课表解析需要 Pillow 与 pytesseract，当前环境未安装。",
        ) from exc

    try:
        image = Image.open(io.BytesIO(image_bytes))
        text = pytesseract.image_to_string(image, lang="chi_sim+eng")
    except Exception as exc:  # noqa: BLE001 - Tesseract 未安装时会抛出多种运行时错误
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"图片 OCR 识别失败：{exc}。请确认已安装 Tesseract OCR 引擎与中文语言包。",
        ) from exc
    return parse_text_content(text)


def _save_events(events: list[dict[str, str]]) -> None:
    SAVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SAVE_PATH.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")


@router.post("/upload")
async def upload_timetable(request: Request, file: UploadFile = File(...)) -> dict[str, Any]:
    """上传并解析课表文件；解析不出课程时明确返回失败，不写脏数据。"""
    content_bytes = await file.read()
    filename = file.filename or ""
    file_ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""

    try:
        if file_ext == "pdf":
            events = parse_pdf_timetable(content_bytes)
        elif file_ext == "ics":
            events = parse_ics_timetable(content_bytes)
        elif file_ext in {"xlsx", "xls"}:
            events = parse_excel_timetable(content_bytes)
        elif file_ext in {"png", "jpg", "jpeg", "bmp", "gif"}:
            events = parse_image_timetable(content_bytes)
        else:
            try:
                text = content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                text = content_bytes.decode("gbk", errors="replace")
            events = parse_text_content(text)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - 统一转成可读的 400，避免泄漏栈信息
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"文件处理失败：{exc}") from exc

    if not events:
        return {
            "success": False,
            "message": f"未能从 {filename} 中识别出课程信息，请检查文件格式是否为“星期 时间 课程 地点 教师”。",
            "events": [],
        }
    _save_events(events)
    return {"success": True, "message": f"成功从 {filename} 解析 {len(events)} 个课程", "events": events}


@router.get("/saved")
async def get_saved_timetable() -> dict[str, Any]:
    """读取上一次成功解析并保存的课表。"""
    if SAVE_PATH.exists():
        events = json.loads(SAVE_PATH.read_text(encoding="utf-8"))
        return {"success": True, "events": events, "message": f"已加载 {len(events)} 个课程"}
    return {"success": True, "events": [], "message": "暂无保存的课表"}


@router.post("/parse-text")
async def parse_text_timetable(request: Request, body: dict[str, str]) -> dict[str, Any]:
    """解析粘贴的课表文本，并覆盖保存。"""
    content = body.get("content", "")
    if not content.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="内容不能为空")

    events = parse_text_content(content)
    if not events:
        return {
            "success": False,
            "message": "没有识别到课程。请按“周一 08:00-09:40 高等数学 A101 张教授”的格式每行写一门课。",
            "events": [],
        }
    _save_events(events)
    return {"success": True, "message": f"解析 {len(events)} 个课程", "events": events}
