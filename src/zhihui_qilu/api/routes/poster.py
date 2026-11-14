"""学术海报生成接口（定向命题六）。

两个入口：
- `/build` 返回结构化结果（含 html 字符串），前端拿去做实时预览和体检清单；
- `/export` 直接回一个 .html 附件，双击就能在浏览器里打开、Ctrl+P 存成 PDF。
"""

from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response

from zhihui_qilu.poster_models import PosterRequest
from zhihui_qilu.poster_service import PosterService

router = APIRouter(prefix="/api/v1/poster", tags=["poster"])

_service = PosterService()


@router.get("/sizes")
async def list_sizes() -> dict[str, Any]:
    """可选的纸张尺寸，前端下拉直接用。"""
    from zhihui_qilu.poster_service import SIZES

    return {
        "success": True,
        "data": {
            "sizes": [
                {"id": key, "label": label, "width_mm": width, "height_mm": height}
                for key, (width, height, label) in SIZES.items()
            ]
        },
    }


@router.post("/build")
async def build_poster(body: PosterRequest) -> dict[str, Any]:
    """生成海报方案：排版结果 + 内容体检。"""
    if not body.sections:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少写一栏内容，比如「结论」")
    plan = _service.build(body)
    return {
        "success": True,
        "message": f"已生成 {plan.size_label}",
        "data": plan.model_dump(mode="json"),
    }


@router.post("/export")
async def export_poster(body: PosterRequest) -> Response:
    """下载可打印的 HTML。文件名用 ASCII，避免不同浏览器对中文文件名的处理差异。"""
    if not body.sections:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少写一栏内容，比如「结论」")
    plan = _service.build(body)
    filename = f"academic-poster-{plan.size}.html"
    return Response(
        content=plan.html,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
