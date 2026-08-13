"""File upload and AI-powered timetable parsing API routes."""

import json
import io
import re
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/timetable", tags=["timetable"])


class TimetableEvent(BaseModel):
    """Parsed timetable event."""
    title: str
    starts_at: str
    ends_at: str
    location: str = ""
    day_of_week: str = ""
    teacher: str = ""


def parse_pdf_timetable(pdf_bytes: bytes) -> list[dict[str, str]]:
    """Parse PDF timetable by directly reading table structure."""
    import pdfplumber
    
    # 节次时间映射
    slot_times = {
        '1': ('08:20', '09:55'),
        '2': ('08:20', '09:55'),
        '3': ('10:10', '11:45'),
        '4': ('10:10', '11:45'),
        '5': ('14:00', '15:35'),
        '6': ('14:00', '15:35'),
        '7': ('15:50', '17:25'),
        '8': ('15:50', '17:25'),
        '9': ('19:00', '20:35'),
        '10': ('19:00', '20:35')
    }
    
    # 星期映射（列索引 -> 星期几）
    day_map = {
        2: '周一', 3: '周二', 4: '周三', 5: '周四', 6: '周五', 7: '周六', 8: '周日'
    }
    
    events = []
    seen = set()  # 去重
    
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            
            for table in tables:
                for row in table:
                    if not row or len(row) < 3:
                        continue
                    
                    # 获取节次信息
                    slot = str(row[1]).strip() if row[1] else ''
                    if slot not in slot_times:
                        continue
                    
                    start_time, end_time = slot_times[slot]
                    
                    # 遍历星期列
                    for col_idx in range(2, min(len(row), 9)):
                        cell = row[col_idx]
                        if not cell or len(str(cell).strip()) < 5:
                            continue
                        
                        cell_text = str(cell)
                        
                        # 提取课程名称
                        title = ''
                        if '★' in cell_text:
                            title = cell_text.split('★')[0].strip()
                        else:
                            lines = cell_text.split('\n')
                            title = lines[0].strip()
                        
                        # 清理课程名称
                        title = re.sub(r'\s+', ' ', title).strip()
                        if not title or len(title) < 2:
                            continue
                        
                        # 提取教师
                        teacher = ''
                        if '教师:' in cell_text:
                            teacher_part = cell_text.split('教师:')[1]
                            if '/' in teacher_part:
                                teacher = teacher_part.split('/')[0].strip()
                            else:
                                teacher = teacher_part.split('\n')[0].strip()
                            # 清理教师名称
                            teacher = re.sub(r'教学班.*', '', teacher).strip()
                        
                        # 提取地点
                        location = ''
                        if '场地:' in cell_text:
                            location_part = cell_text.split('场地:')[1]
                            if '/' in location_part:
                                location = location_part.split('/')[0].strip()
                            else:
                                location = location_part.split('\n')[0].strip()
                        
                        day = day_map.get(col_idx, '周一')
                        
                        # 去重
                        key = f"{day}_{title}"
                        if key in seen:
                            continue
                        seen.add(key)
                        
                        events.append({
                            'title': title,
                            'starts_at': f'2026-09-01T{start_time}:00',
                            'ends_at': f'2026-09-01T{end_time}:00',
                            'location': location,
                            'day_of_week': day,
                            'teacher': teacher
                        })
    
    return events


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text from PDF file using pdfplumber."""
    try:
        import pdfplumber
        
        text_parts = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
        
        return "\n".join(text_parts)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"PDF解析失败: {str(e)}"
        )


def extract_text_from_excel(excel_bytes: bytes) -> str:
    """Extract text from Excel file."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(excel_bytes), read_only=True)
        text_parts = []
        for sheet in wb.worksheets:
            for row in sheet.iter_rows(values_only=True):
                row_text = " ".join([str(cell) if cell else "" for cell in row])
                if row_text.strip():
                    text_parts.append(row_text)
        wb.close()
        return "\n".join(text_parts)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Excel解析失败: {str(e)}"
        )


async def parse_with_deepseek(content: str, provider: Any) -> list[dict[str, str]]:
    """Use DeepSeek to parse timetable content."""
    from zhihui_qilu.ai.provider import ChatMessage
    
    system_prompt = """你是一个课表解析助手。请从用户提供的课表数据中提取课程信息。

【节次时间对应】
- 第1-2节：08:20-09:55
- 第3-4节：10:10-11:45
- 第5-6节：14:00-15:35
- 第7-8节：15:50-17:25
- 第9-10节：19:00-20:35

【提取规则】
1. 课程名称：提取★前面的文字
2. 星期几：根据课程在表格中的列位置确定
3. 地点：提取"场地:"后面的内容
4. 教师：提取"教师:"后面的内容
5. 日期：使用2026年9月第一周

只返回JSON数组格式。"""

    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=f"请解析以下课表内容：\n\n{content}")
    ]
    
    try:
        response = await provider.complete(messages, temperature=0.1)
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        if response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()
        
        events = json.loads(response)
        
        for event in events:
            if not event.get("title"):
                event["title"] = "未知课程"
            if event.get("day_of_week") not in ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]:
                event["day_of_week"] = "周一"
        
        return events
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI解析失败: {str(e)}"
        )


@router.post("/upload")
async def upload_timetable(
    request: Request,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Upload and parse a timetable file."""
    try:
        content_bytes = await file.read()
        filename = file.filename or ""
        file_ext = filename.lower().split(".")[-1] if "." in filename else ""
        
        if file_ext == "pdf":
            # 优先使用表格解析
            events = parse_pdf_timetable(content_bytes)
            if events:
                return {
                    "success": True,
                    "message": f"成功从 {filename} 解析 {len(events)} 个课程",
                    "events": events
                }
            # 如果表格解析失败，使用文本解析+AI
            content = extract_text_from_pdf(content_bytes)
        elif file_ext in ["xlsx", "xls"]:
            content = extract_text_from_excel(content_bytes)
        elif file_ext == "csv":
            try:
                content = content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                content = content_bytes.decode("gbk")
        else:
            try:
                content = content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    content = content_bytes.decode("gbk")
                except UnicodeDecodeError:
                    content = content_bytes.decode("gb2312")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"文件读取失败: {str(e)}"
        )
    
    if not content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件内容为空或无法解析"
        )
    
    container = request.app.state.container
    provider = container.ai_provider
    
    if not provider.available:
        return {
            "success": True,
            "message": f"当前为离线模式，已解析文件：{filename}。",
            "events": []
        }
    
    events = await parse_with_deepseek(content, provider)
    
    return {
        "success": True,
        "message": f"成功从 {filename} 解析 {len(events)} 个课程",
        "events": events
    }


@router.post("/parse-text")
async def parse_text_timetable(
    request: Request,
    body: dict[str, str],
) -> dict[str, Any]:
    """Parse timetable from text using AI."""
    content = body.get("content", "")
    
    if not content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="内容不能为空"
        )
    
    container = request.app.state.container
    provider = container.ai_provider
    
    if not provider.available:
        return {
            "success": True,
            "message": "当前为离线模式。",
            "events": []
        }
    
    events = await parse_with_deepseek(content, provider)
    
    return {
        "success": True,
        "message": f"成功解析 {len(events)} 个课程",
        "events": events
    }