"""Document export API routes."""

import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


class DocumentElements(BaseModel):
    reference_number: str = ""
    title: str = ""
    body: str = ""
    signature: str = ""
    issue_date: str = ""


@router.post("/export-docx")
async def export_docx(body: DocumentElements, request: Request) -> FileResponse:
    """Export document as DOCX."""
    from zhihui_qilu.document_models import OfficialDocumentElements
    from zhihui_qilu.document_service import AdministrativeDocxEngine
    
    elements = OfficialDocumentElements(
        reference_number=body.reference_number,
        title=body.title,
        body=body.body,
        signature=body.signature,
        issue_date=body.issue_date
    )
    
    engine = AdministrativeDocxEngine()
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir) / f"{body.title or 'document'}.docx"
        engine.render(elements, output_path)
        
        if not output_path.exists():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="DOCX生成失败"
            )
        
        return FileResponse(
            path=output_path,
            filename=f"{body.title or 'document'}.docx",
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )