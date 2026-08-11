"""Safe conversational endpoints for the guide and AI interview room."""

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from zhihui_qilu.ai.service import ConversationMode
from zhihui_qilu.api.dependencies import get_development_context
from zhihui_qilu.core.errors import PlatformError
from zhihui_qilu.core.models import AgentRequest, RequestContext

router = APIRouter(prefix="/api/v1/chat", tags=["conversation"])


class ChatBody(BaseModel):
    """One user message plus bounded, non-authoritative UI metadata."""

    mode: ConversationMode = "wellbeing"
    message: str = Field(min_length=1, max_length=4_000)
    metadata: dict[str, str] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    """Non-streaming conversation response used by simple clients and tests."""

    reply: str
    state: Literal["talking", "caring", "thinking"]
    escalated: bool
    provider_online: bool


@router.get("/history")
async def get_history(
    request: Request,
    mode: ConversationMode = "wellbeing",
    context: RequestContext = Depends(get_development_context),
) -> dict[str, object]:
    """Return the current user's recent session conversation only."""
    messages = await request.app.state.container.conversation.history(mode=mode, user_id=context.user_id, session_id=context.session_id)
    return {"messages": [message.model_dump() for message in messages]}


@router.post("", response_model=ChatResponse)
async def create_chat(
    body: ChatBody,
    request: Request,
    context: RequestContext = Depends(get_development_context),
) -> ChatResponse:
    """Generate one safe assistant turn through the configured provider."""
    try:
        inspected = request.app.state.container.security_gateway.inspect_request(AgentRequest(capability="conversation", text=body.message, context=context))
        result = await request.app.state.container.conversation.reply(mode=body.mode, user_id=context.user_id, session_id=context.session_id, message=inspected.text, metadata=body.metadata)
        return ChatResponse(reply=result.reply, state=result.state, escalated=result.escalated, provider_online=result.provider_online)
    except PlatformError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/stream")
async def stream_chat(
    body: ChatBody,
    request: Request,
    context: RequestContext = Depends(get_development_context),
) -> StreamingResponse:
    """Stream text deltas as server-sent events while preserving the same safety boundary."""
    try:
        inspected = request.app.state.container.security_gateway.inspect_request(AgentRequest(capability="conversation", text=body.message, context=context))
    except PlatformError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    async def events():
        async for event_type, value in request.app.state.container.conversation.stream(
            mode=body.mode,
            user_id=context.user_id,
            session_id=context.session_id,
            message=inspected.text,
            metadata=body.metadata,
        ):
            yield f"data: {json.dumps({'type': event_type, 'value': value}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
