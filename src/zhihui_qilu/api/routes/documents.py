"""公文 DOCX 导出与上传规范化路由。

渲染结果必须活到响应发送完成，所以临时文件用 ``mkstemp`` 创建、由 ``BackgroundTask``
在响应结束后删除；早期版本用 ``TemporaryDirectory`` 上下文，目录在 return 时就被清掉，
导致下载 500。

规范化是两步：``POST /normalize`` 上传并返回改动清单 + 一次性 token，
``GET /normalize/{token}`` 凭 token 下载改好的文件。清单里每一处改动都带依据，
前端要逐条展示，所以不能塞进响应头。
"""

import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from zhihui_qilu.doc_normalizer import NormalizeError, normalize_docx
from zhihui_qilu.document_models import OfficialDocumentElements
from zhihui_qilu.document_phrases import phrase_payload
from zhihui_qilu.document_service import AdministrativeDocxEngine
from zhihui_qilu.document_templates import BANNERS, TEMPLATE_CATALOG

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

# 规范化结果留 30 分钟，够演示时反复下载，又不至于把临时目录堆满。
_NORMALIZED_TTL_SECONDS = 1800
# 上传上限：一份公文几十页也就几 MB，20MB 足够挡住误传的大文件。
_MAX_UPLOAD_BYTES = 20 * 1024 * 1024
_NORMALIZED: dict[str, tuple[Path, str, float]] = {}


class DocumentElements(BaseModel):
    """前端提交的公文要素。标题与正文是渲染的最低要求。

    其余字段对应《山东师范大学行政文件格式细则》的版式项：版头、主送机关、附件、
    抄送、主题词、密级、紧急程度、签发人、结束语、印发机关。
    """

    reference_number: str = ""
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1)
    signature: str = ""
    issue_date: str = ""

    doc_type: str = "notice"
    banner_name: str = ""
    recipient: str = ""
    attachments: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    urgency: str = ""
    secrecy: str = ""
    signer: str = ""
    closing: str = ""
    print_agency: str = ""


@router.get("/templates")
async def list_templates() -> dict[str, Any]:
    """返回公文文种模板库与版头选项，作为前端唯一数据源。"""
    return {"success": True, "data": {"templates": TEMPLATE_CATALOG, "banners": BANNERS}}


@router.get("/phrases")
async def list_phrases() -> dict[str, Any]:
    """返回起草助手用的句式库、文种指引、易混对照与报送时限。

    与模板库同源放在后端：文种 id 必须和 TEMPLATE_CATALOG 对得上，
    两处各写一份迟早会走样。
    """
    return {"success": True, "data": phrase_payload()}


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
        doc_type=body.doc_type or "notice",
        banner_name=body.banner_name or None,
        recipient=body.recipient or None,
        attachments=[item for item in body.attachments if item.strip()],
        cc=[item for item in body.cc if item.strip()],
        keywords=[item for item in body.keywords if item.strip()],
        urgency=body.urgency or None,
        secrecy=body.secrecy or None,
        signer=body.signer or None,
        closing=body.closing or None,
        print_agency=body.print_agency or None,
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


def _prune_normalized() -> None:
    """清掉过期的规范化结果，顺手把临时文件删掉。"""
    now = time.time()
    for token, (path, _name, expires_at) in list(_NORMALIZED.items()):
        if expires_at <= now:
            _NORMALIZED.pop(token, None)
            try:
                path.unlink()
            except OSError:
                pass


@router.post("/normalize")
async def normalize_upload(
    file: UploadFile = File(...),
    doc_type: str = Form("notice"),
) -> dict[str, Any]:
    """上传一份已经写好的公文，按国标重排版式，返回改动清单与一次性下载 token。

    这条路径对应定向命题三的「上传 → 选文种 → 一键规范化」：不改一个字，
    只把字体字号、行距、页边距、标题层级、序号编号、页眉页脚、落款日期改到合规。
    """
    _prune_normalized()

    original = (file.filename or "document.docx").strip()
    suffix = Path(original).suffix.lower()
    if suffix not in {".docx", ".doc"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只接 .docx 和 .doc。如果手上是 PDF，先用 Word 打开另存为 .docx。",
        )

    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件是空的，没东西可改。")
    if len(payload) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"文件 {len(payload) / 1024 / 1024:.1f}MB，超过 20MB 上限。",
        )

    stem = _safe_filename(Path(original).stem)
    src_path: str | None = None
    out_path: str | None = None
    try:
        src_handle, src_path = tempfile.mkstemp(suffix=".docx", prefix="zhq-src-")
        with os.fdopen(src_handle, "wb") as handle:
            handle.write(payload)
        out_handle, out_path = tempfile.mkstemp(suffix=".docx", prefix="zhq-norm-")
        os.close(out_handle)
        outcome = normalize_docx(Path(src_path), Path(out_path), doc_type=doc_type)
    except NormalizeError as exc:
        if out_path:
            _remove_file(out_path)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - 兜底，避免半成品文件留在临时目录
        if out_path:
            _remove_file(out_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"规范化失败：{exc}"
        ) from exc
    finally:
        if src_path:
            _remove_file(src_path)

    token = uuid.uuid4().hex
    filename = f"{stem}-规范化.docx"
    _NORMALIZED[token] = (Path(out_path), filename, time.time() + _NORMALIZED_TTL_SECONDS)

    data = outcome.as_dict()
    data["token"] = token
    data["filename"] = filename
    data["expires_in"] = _NORMALIZED_TTL_SECONDS
    message = (
        f"已按{outcome.doc_type_name}版式重排 {outcome.total_changes} 处，正文一个字没改"
        if outcome.total_changes
        else "这份文档已经符合版式要求，没有需要改的地方"
    )
    return {"success": True, "message": message, "data": data}


@router.get("/normalize/{token}")
async def download_normalized(token: str) -> FileResponse:
    """凭上传时拿到的 token 下载改好的文件；过期就让人重传，不猜。"""
    entry = _NORMALIZED.get(token)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="下载链接已过期，请重新上传。")
    path, filename, expires_at = entry
    if expires_at <= time.time() or not path.exists():
        _NORMALIZED.pop(token, None)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="下载链接已过期，请重新上传。")
    return FileResponse(path=path, filename=filename, media_type=DOCX_MEDIA_TYPE)
