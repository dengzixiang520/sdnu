"""Authenticated development bridge from the web client to registered Agent Skills."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, ValidationError

from zhihui_qilu.api.dependencies import get_development_context
from zhihui_qilu.core.errors import PlatformError
from zhihui_qilu.core.models import AgentRequest, AgentResponse, RequestContext

router = APIRouter(prefix="/api/v1", tags=["agent"])


class AgentCommandBody(BaseModel):
    """HTTP representation of an explicitly requested, bounded Skill action."""

    capability: str = Field(min_length=1, max_length=100)
    action: str = Field(min_length=1, max_length=100)
    text: str = Field(default="", max_length=5_000)
    payload: dict[str, Any] = Field(default_factory=dict)


@router.post("/commands", response_model=AgentResponse)
async def execute_command(
    body: AgentCommandBody,
    request: Request,
    context: RequestContext = Depends(get_development_context),
) -> AgentResponse:
    """Run an allow-listed Skill action through the same security gateway as all callers."""
    payload = {**body.payload, "action": body.action}
    try:
        return await request.app.state.container.router.execute(AgentRequest(capability=body.capability, text=body.text, payload=payload, context=context))
    except ValidationError as exc:
        # 业务模型校验失败属于调用方参数问题，应回 4xx 并说明哪个字段不对，
        # 而不是冒泡成 500 让前端只看到"服务器错误"。
        fields = "、".join(str(item["loc"][-1]) for item in exc.errors() if item.get("loc")) or "参数"
        raise HTTPException(
            status_code=422,
            detail=f"请求参数不合法：{fields}",
        ) from exc
    except PlatformError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
