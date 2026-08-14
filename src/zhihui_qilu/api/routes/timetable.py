import json
import io
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/timetable", tags=["timetable"])


class TimetableEvent(BaseModel):
    title: str
    starts_at: str
    ends_at: str
    location: str = ""
    day_of_week: str = ""
    teacher: str = ""


def parse_pdf_timetable(pdf_bytes: bytes) -> list[dict[str, str]]:
    """Parse PDF timetable."""
    import pdfplumber
    # ... existing code ...
    return []


def parse_excel_timetable(excel_bytes: bytes) -> list[dict[str, str]]:
    """Parse Excel timetable."""
    import openpyxl
    
    events = []
    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes), read_only=True)
    
    for sheet in wb.worksheets:
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            continue
        
        # 假设第一行是标题
        headers = [str(h).lower() if h else "" for h in rows[0]]
        
        # 查找列索引
        day_col = next((i for i, h in enumerate(headers) if "星期" in h or "day" in h), None)
        time_col = next((i for i, h in enumerate(headers) if "时间" in h or "time" in h), None)
        name_col = next((i for i, h in enumerate(headers) if "课程" in h or "名称" in h or "name" in h), None)
        location_col = next((i for i, h in enumerate(headers) if "地点" in h or "教室" in h or "location" in h), None)
        teacher_col = next((i for i, h in enumerate(headers) if "教师" in h or "老师" in h or "teacher" in h), None)
        
        # 时间映射
        time_map = {
            "1": ("08:20", "09:05"), "2": ("09:10", "09:55"),
            "3": ("10:10", "10:55"), "4": ("11:00", "11:45"),
            "5": ("14:00", "14:45"), "6": ("14:50", "15:35"),
            "7": ("15:50", "16:35"), "8": ("16:40", "17:25"),
            "9": ("19:00", "19:45"), "10": ("19:50", "20:35"),
        }
        
        day_map = {"周一": "周一", "周一": "周一", "monday": "周一", "mon": "周一",
                   "周二": "周二", "tuesday": "周二", "tue": "周二",
                   "周三": "周三", "wednesday": "周三", "wed": "周三",
                   "周四": "周四", "thursday": "周四", "thu": "周四",
                   "周五": "周五", "friday": "周五", "fri": "周五",
                   "周六": "周六", "saturday": "周六", "sat": "周六",
                   "周日": "周日", "sunday": "周日", "sun": "周日"}
        
        for row in rows[1:]:
            if not row or not any(row):
                continue
            
            try:
                day = str(row[day_col]) if day_col is not None and day_col < len(row) else ""
                time_str = str(row[time_col]) if time_col is not None and time_col < len(row) else ""
                name = str(row[name_col]) if name_col is not None and name_col < len(row) else ""
                location = str(row[location_col]) if location_col is not None and location_col < len(row) else ""
                teacher = str(row[teacher_col]) if teacher_col is not None and teacher_col < len(row) else ""
                
                if not name or name == "None":
                    continue
                
                # 解析时间
                start_time, end_time = "08:20", "09:05"
                for slot, (s, e) in time_map.items():
                    if slot in time_str:
                        start_time, end_time = s, e
                        break
                
                # 解析星期
                day_of_week = "周一"
                for d, v in day_map.items():
                    if d in day.lower():
                        day_of_week = v
                        break
                
                events.append({
                    "title": name,
                    "starts_at": f"2026-09-01T{start_time}:00",
                    "ends_at": f"2026-09-01T{end_time}:00",
                    "location": location,
                    "day_of_week": day_of_week,
                    "teacher": teacher
                })
            except Exception:
                continue
    
    wb.close()
    return events


def parse_image_timetable(image_bytes: bytes) -> list[dict[str, str]]:
    """Parse image timetable using OCR."""
    try:
        from PIL import Image
        import pytesseract
        
        image = Image.open(io.BytesIO(image_bytes))
        text = pytesseract.image_to_string(image, lang='chi_sim+eng')
        
        if not text.strip():
            return []
        
        # 使用文本解析
        return parse_text_content(text)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"图片OCR识别失败: {str(e)}. 请确保已安装Tesseract OCR引擎。"
        )


def parse_text_content(text: str) -> list[dict[str, str]]:
    """Parse text content to extract timetable events."""
    events = []
    lines = text.strip().split('\n')
    
    time_map = {
        "1": ("08:20", "09:05"), "2": ("09:10", "09:55"),
        "3": ("10:10", "10:55"), "4": ("11:00", "11:45"),
        "5": ("14:00", "14:45"), "6": ("14:50", "15:35"),
        "7": ("15:50", "16:35"), "8": ("16:40", "17:25"),
        "9": ("19:00", "19:45"), "10": ("19:50", "20:35"),
    }
    
    day_map = {"周一": "周一", "周二": "周二", "周三": "周三", "周四": "周四", "周五": "周五", "周六": "周六", "周日": "周日"}
    
    for line in lines:
        # 尝试匹配格式：星期 时间 课程 地点 教师
        match = re.search(r'(周[一二三四五六日])\s*(\d+[-节]?\d*)\s*(.+?)(?:\s*@\s*|\s+)(.+?)(?:\s+|$)', line)
        if match:
            day = match.group(1)
            time_slot = match.group(2)
            name = match.group(3).strip()
            location = match.group(4).strip()
            
            start_time, end_time = "08:20", "09:05"
            for slot, (s, e) in time_map.items():
                if slot in time_slot:
                    start_time, end_time = s, e
                    break
            
            events.append({
                "title": name,
                "starts_at": f"2026-09-01T{start_time}:00",
                "ends_at": f"2026-09-01T{end_time}:00",
                "location": location,
                "day_of_week": day_map.get(day, "周一"),
                "teacher": ""
            })
    
    return events


@router.post("/upload")
async def upload_timetable(request: Request, file: UploadFile = File(...)) -> dict[str, Any]:
    """Upload and parse a timetable file."""
    try:
        content_bytes = await file.read()
        filename = file.filename or ""
        file_ext = filename.lower().split(".")[-1] if "." in filename else ""
        
        events = []
        
        if file_ext == "pdf":
            events = parse_pdf_timetable(content_bytes)
        elif file_ext in ["xlsx", "xls"]:
            events = parse_excel_timetable(content_bytes)
        elif file_ext in ["png", "jpg", "jpeg", "bmp", "gif"]:
            events = parse_image_timetable(content_bytes)
        elif file_ext == "csv":
            try:
                text = content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                text = content_bytes.decode("gbk")
            events = parse_text_content(text)
        else:
            # 尝试作为文本解析
            try:
                text = content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                text = content_bytes.decode("gbk")
            events = parse_text_content(text)
        
        if events:
            # 保存到文件
            save_path = Path("./data/timetable.json")
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
            
            return {
                "success": True,
                "message": f"成功从 {filename} 解析 {len(events)} 个课程",
                "events": events
            }
        else:
            return {
                "success": False,
                "message": f"未能从 {filename} 中识别出课程信息，请检查文件格式",
                "events": []
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"文件处理失败: {str(e)}"
        )


@router.get("/saved")
async def get_saved_timetable() -> dict[str, Any]:
    """Get saved timetable."""
    save_path = Path("./data/timetable.json")
    if save_path.exists():
        events = json.loads(save_path.read_text(encoding="utf-8"))
        return {"success": True, "events": events, "message": f"已加载 {len(events)} 个课程"}
    return {"success": True, "events": [], "message": "暂无保存的课表"}


@router.post("/parse-text")
async def parse_text_timetable(request: Request, body: dict[str, str]) -> dict[str, Any]:
    """Parse timetable from text."""
    content = body.get("content", "")
    if not content.strip():
        raise HTTPException(status_code=400, detail="内容不能为空")
    
    events = parse_text_content(content)
    
    if events:
        save_path = Path("./data/timetable.json")
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
    
    return {"success": True, "message": f"解析 {len(events)} 个课程", "events": events}