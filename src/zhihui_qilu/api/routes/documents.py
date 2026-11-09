"""公文 DOCX 导出路由。

渲染结果必须活到响应发送完成，所以临时文件用 ``mkstemp`` 创建、由 ``BackgroundTask``
在响应结束后删除；早期版本用 ``TemporaryDirectory`` 上下文，目录在 return 时就被清掉，
导致下载 500。
"""

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from zhihui_qilu.document_models import OfficialDocumentElements
from zhihui_qilu.document_service import AdministrativeDocxEngine

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class DocumentElements(BaseModel):
    """前端提交的公文要素。标题与正文是渲染的最低要求。"""

    reference_number: str = ""
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1)
    signature: str = ""
    issue_date: str = ""


def _safe_filename(title: str) -> str:
    """去掉路径分隔符与 Windows 保留字符，避免写文件或响应头被污染。"""
    cleaned = "".join("_" if char in '\\/:*?"<>|' else char for char in title).strip()
    return (cleaned or "document")[:80]


def _remove_file(path: str) -> None:
    """响应发送完成后清理临时文件；失败不影响已经返回的下载。"""
    try:
        os.unlink(path)
    except OSError:
        pass


@router.post("/export-docx")
async def export_docx(body: DocumentElements, background_tasks: BackgroundTasks) -> FileResponse:
    """把公文要素渲染为 DOCX 并流式返回。"""
    elements = OfficialDocumentElements(
        reference_number=body.reference_number or None,
        title=body.title,
        body=body.body,
        signature=body.signature or None,
        issue_date=body.issue_date or None,
    )
    stem = _safe_filename(body.title)

    try:
        handle, temp_path = tempfile.mkstemp(suffix=".docx", prefix="zhq-doc-")
        os.close(handle)
        AdministrativeDocxEngine().render(elements, Path(temp_path))
    except OSError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"DOCX 生成失败：{exc}") from exc

    background_tasks.add_task(_remove_file, temp_path)
    return FileResponse(path=temp_path, filename=f"{stem}.docx", media_type=DOCX_MEDIA_TYPE)
