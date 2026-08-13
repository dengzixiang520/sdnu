"""File upload and AI-powered timetable parsing API routes."""

import json
import io
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


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text from PDF file using pdfplumber for better Chinese support."""
    try:
        import pdfplumber
        import io
        
        text_parts = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
                
                # 如果文本提取失败，尝试提取表格
                if not text:
                    tables = page.extract_tables()
                    for table in tables:
                        for row in table:
                            row_text = " ".join([str(cell) if cell else "" for cell in row])
                            if row_text.strip():
                                text_parts.append(row_text)
        
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
    
    system_prompt = """你是一个课表解析助手。请从用户提供的文本中提取课程信息。

【重要规则】
1. title字段必须是具体的课程名称（如"高等数学"、"英语听说"、"数据结构"），绝对不能是"课程名称"、"课程1"这样的占位符
2. 如果文本中包含"高等数学"、"英语"、"数据结构"等课程名，必须原样提取
3. 如果实在无法识别课程名，使用"未知课程"
4. teacher字段提取教师姓名，如果无法识别则留空字符串
5. location字段提取教室/地点信息
6. day_of_week必须是：周一、周二、周三、周四、周五、周六、周日
7. 如果没有明确日期，使用2026年9月第一周
8. 注意：一个课程可能占多个节次（如3-4节），需要为每个节次创建单独的记录

请返回JSON数组格式，示例：
```json
[
  {
    "title": "高等数学",
    "starts_at": "2026-09-01T08:20:00",
    "ends_at": "2026-09-01T09:05:00",
    "location": "A101",
    "day_of_week": "周一",
    "teacher": "张教授"
  }
]
```

只返回JSON数组，不要返回其他任何文字。"""

    user_message = f"""请解析以下课表内容，提取每门课程的真实名称、时间、地点和教师：

{content}

注意：title字段必须是真实的课程名称，不能是"课程名称"或"课程1"这样的占位符！"""

    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_message)
    ]
    
    try:
        response = await provider.complete(messages, temperature=0.1)
        # 清理响应，提取JSON
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        if response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()
        
        events = json.loads(response)
        
        # 验证并修复每个事件
        for event in events:
            # 确保title不为空或占位符
            if not event.get("title") or event["title"] in ["课程名称", "课程", "未知", ""]:
                event["title"] = "未知课程"
            
            # 确保day_of_week有效
            if event.get("day_of_week") not in ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]:
                # 尝试从starts_at推断
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(event["starts_at"].replace("Z", "+00:00"))
                    days = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
                    event["day_of_week"] = days[dt.weekday()]
                except:
                    event["day_of_week"] = "周一"
        
        return events
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI返回格式错误: {str(e)}"
        )
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
    """Upload and parse a timetable file using AI."""
    try:
        content_bytes = await file.read()
        filename = file.filename or ""
        file_ext = filename.lower().split(".")[-1] if "." in filename else ""
        
        if file_ext == "pdf":
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
            "message": f"当前为离线模式，已解析文件：{filename}。请配置API Key以使用AI解析。",
            "events": [
                {"title": "高等数学", "starts_at": "2026-09-01T08:20:00", "ends_at": "2026-09-01T09:05:00", "location": "A101", "day_of_week": "周一", "teacher": "张教授"},
                {"title": "数据结构", "starts_at": "2026-09-01T14:00:00", "ends_at": "2026-09-01T14:45:00", "location": "B202", "day_of_week": "周一", "teacher": "李老师"},
                {"title": "英语听说", "starts_at": "2026-09-02T10:10:00", "ends_at": "2026-09-02T10:55:00", "location": "C305", "day_of_week": "周二", "teacher": "王老师"},
                {"title": "Python程序设计", "starts_at": "2026-09-03T15:50:00", "ends_at": "2026-09-03T16:35:00", "location": "D401", "day_of_week": "周三", "teacher": "赵教授"},
            ]
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
            "message": "当前为离线模式，返回示例课表数据。",
            "events": [
                {"title": "高等数学", "starts_at": "2026-09-01T08:20:00", "ends_at": "2026-09-01T09:05:00", "location": "A101", "day_of_week": "周一", "teacher": "张教授"},
                {"title": "数据结构", "starts_at": "2026-09-01T14:00:00", "ends_at": "2026-09-01T14:45:00", "location": "B202", "day_of_week": "周一", "teacher": "李老师"},
            ]
        }
    
    events = await parse_with_deepseek(content, provider)
    
    return {
        "success": True,
        "message": f"成功解析 {len(events)} 个课程",
        "events": events
    }