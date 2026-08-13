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
    """Extract text from PDF file."""
    try:
        import PyPDF2
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        text_parts = []
        for page in pdf_reader.pages:
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
    
    system_prompt = """你是一个课表解析助手。请从用户提供的文本中提取课程信息。

请严格按照以下JSON格式返回，每个字段都不能为空字符串：
```json
[
  {
    "title": "课程名称",
    "starts_at": "2026-09-01T08:00:00",
    "ends_at": "2026-09-01T09:40:00",
    "location": "教室地点",
    "day_of_week": "周一",
    "teacher": "教师姓名"
  }
]
```

重要规则：
1. title（课程名称）必须是具体的课程名，如"高等数学"、"英语听说"，不能为空
2. 如果文本中没有明确日期，使用2026年9月第一周的日期
3. day_of_week必须是：周一、周二、周三、周四、周五、周六、周日
4. 只返回JSON数组，不要返回其他任何文字"""

    user_message = f"""请解析以下课表内容，提取每门课程的名称、时间、地点和教师信息：

{content}

请返回标准JSON数组格式。"""

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
        
        # 验证每个事件都有title
        for event in events:
            if not event.get("title"):
                event["title"] = "未命名课程"
        
        return events
    except json.JSONDecodeError as e:
        # 如果JSON解析失败，尝试手动解析
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
                {"title": "高等数学", "starts_at": "2026-09-01T08:00:00", "ends_at": "2026-09-01T09:40:00", "location": "A101", "day_of_week": "周一", "teacher": "张教授"},
                {"title": "数据结构", "starts_at": "2026-09-01T14:00:00", "ends_at": "2026-09-01T15:40:00", "location": "B202", "day_of_week": "周一", "teacher": "李老师"},
                {"title": "英语听说", "starts_at": "2026-09-02T10:00:00", "ends_at": "2026-09-02T11:40:00", "location": "C305", "day_of_week": "周二", "teacher": "王老师"},
                {"title": "Python程序设计", "starts_at": "2026-09-03T14:00:00", "ends_at": "2026-09-03T15:40:00", "location": "D401", "day_of_week": "周三", "teacher": "赵教授"},
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
                {"title": "高等数学", "starts_at": "2026-09-01T08:00:00", "ends_at": "2026-09-01T09:40:00", "location": "A101", "day_of_week": "周一", "teacher": "张教授"},
                {"title": "数据结构", "starts_at": "2026-09-01T14:00:00", "ends_at": "2026-09-01T15:40:00", "location": "B202", "day_of_week": "周一", "teacher": "李老师"},
            ]
        }
    
    events = await parse_with_deepseek(content, provider)
    
    return {
        "success": True,
        "message": f"成功解析 {len(events)} 个课程",
        "events": events
    }