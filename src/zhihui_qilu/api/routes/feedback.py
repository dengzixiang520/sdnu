"""学生评价路由：记录「有用 / 没用」，并给出聚合有用率。

写接口需要开发身份头；读接口公开，因为它只出汇总数字，不含任何人的原文。
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from zhihui_qilu.api.dependencies import get_development_context
from zhihui_qilu.core.models import RequestContext
from zhihui_qilu.feedback_service import TARGETS

router = APIRouter(prefix="/api/v1/feedback", tags=["feedback"])


class FeedbackInput(BaseModel):
    """一条评价。``helpful`` 必填，``note`` 选填。"""

    target: str = Field(min_length=1, max_length=60)
    helpful: bool
    note: str = Field(default="", max_length=200)


def get_service(request: Request):
    return request.app.state.container.feedback


@router.get("/targets")
async def list_targets() -> dict[str, Any]:
    """可评价对象清单，前端据此渲染按钮，不在前端硬编码中文名。"""
    return {"success": True, "data": {"targets": [{"id": key, "name": name} for key, name in TARGETS.items()]}}


@router.post("")
async def submit_feedback(
    body: FeedbackInput,
    request: Request,
    context: RequestContext = Depends(get_development_context),
) -> dict[str, Any]:
    """记一条评价。目标不认识就明确报错，不静默丢弃。"""
    service = get_service(request)
    try:
        data = await service.record(
            user_id=context.user_id,
            session_id=context.session_id,
            target=body.target,
            helpful=body.helpful,
            note=body.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    message = "记下了，谢谢。这条会用来改进同类回答。" if body.helpful else "记下了。能说一句哪里不够，我们改得更准。"
    return {"success": True, "message": message, "data": data}


@router.get("/summary")
async def feedback_summary(request: Request) -> dict[str, Any]:
    """跨用户聚合的有用率，用于展示真实用户评分。"""
    service = get_service(request)
    return {"success": True, "data": await service.summary()}
