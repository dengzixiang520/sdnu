"""学习计划接口：生成一周计划，并按真实完成情况重排剩余几天。

两条接口都是纯函数式的读写（不写库、不读会话），所以不挂身份依赖：
前端用普通 ``fetch`` 调用即可，避免因为缺 ``X-User-Id`` 而 401。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from zhihui_qilu.study_plan_service import (
    AdjustRequest,
    PlanRequest,
    StudyPlan,
    StudyPlanService,
)

router = APIRouter(prefix="/api/v1/study-plan", tags=["study-plan"])


def _service(request: Request) -> StudyPlanService:
    return StudyPlanService(request.app.state.container.ai_provider)


@router.get("/status")
async def plan_status(request: Request) -> dict[str, object]:
    """前端用来决定要不要提示"当前是本地模板"。"""
    container = request.app.state.container
    available = container.ai_provider.available
    return {
        "available": available,
        "model": container.settings.ai_model if available else "offline",
        "note": "计划由大模型按目标与可投入时间生成，失败时自动回落到本地模板"
        if available
        else "未配置 ZHQ_AI_API_KEY，将使用本地模板生成，结构一致但不做个性化拆解",
    }


@router.post("/generate", response_model=StudyPlan)
async def generate_plan(body: PlanRequest, request: Request) -> StudyPlan:
    """从今天起排 7 天。模型失败时仍然返回 200，用 ``source`` 字段标明来源。"""
    return await _service(request).generate(body)


@router.post("/adjust", response_model=StudyPlan)
async def adjust_plan(body: AdjustRequest, request: Request) -> StudyPlan:
    """只重排剩余几天，把已完成与漏掉的任务作为输入条件。"""
    try:
        return await _service(request).adjust(body)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
