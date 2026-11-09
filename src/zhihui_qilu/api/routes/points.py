"""Points and leaderboard API routes.

读接口保持公开；写接口按最小权限收口：手工加分与竞赛加分只允许管理员，
每日打卡在服务端做“一天一次”的限制（前端 localStorage 只是提示，不能作为依据）。
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from zhihui_qilu.api.dependencies import get_development_context
from zhihui_qilu.core.enums import UserRole
from zhihui_qilu.core.models import RequestContext

router = APIRouter(prefix="/api/v1/points", tags=["points"])


class AddPointsRequest(BaseModel):
    user_id: str = Field(min_length=1)
    user_name: str = ""
    points: int = Field(gt=0, le=10_000)
    source: str = Field(default="activity", max_length=40)
    source_detail: str = ""


class CompetitionPointsRequest(BaseModel):
    user_id: str = Field(min_length=1)
    user_name: str = ""
    award_level: str
    competition_name: str


def get_service(request: Request):
    return request.app.state.container.points_service


def require_administrator(context: RequestContext = Depends(get_development_context)) -> RequestContext:
    """积分发放属于管理动作，学生/辅导员不能直接调用。"""
    if context.role != UserRole.ADMINISTRATOR:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅管理员可发放积分")
    return context


@router.get("/leaderboard")
async def get_leaderboard(request: Request, limit: int = 20) -> dict[str, Any]:
    """Get points leaderboard."""
    service = get_service(request)
    leaderboard = service.get_leaderboard(max(1, min(limit, 100)))
    return {"success": True, "data": {"leaderboard": leaderboard}}


@router.get("/user/{user_id}")
async def get_user_points(user_id: str, request: Request) -> dict[str, Any]:
    """Get user points summary."""
    service = get_service(request)
    user = service.get_user_points(user_id)
    if not user:
        return {"success": True, "data": {"user": None, "message": "用户暂无积分记录"}}
    return {"success": True, "data": {"user": user}}


@router.get("/user/{user_id}/records")
async def get_user_records(user_id: str, request: Request, limit: int = 50) -> dict[str, Any]:
    """Get user points records."""
    service = get_service(request)
    records = service.get_user_records(user_id, max(1, min(limit, 200)))
    return {"success": True, "data": {"records": records}}


@router.get("/badges")
async def get_badges(request: Request) -> dict[str, Any]:
    """Get all badge definitions."""
    service = get_service(request)
    return {"success": True, "data": {"badges": service.get_badges()}}


@router.get("/rules")
async def get_points_rules(request: Request) -> dict[str, Any]:
    """Get points rules."""
    service = get_service(request)
    return {"success": True, "data": {"rules": service.get_points_rules()}}


@router.post("/add")
async def add_points(
    body: AddPointsRequest,
    request: Request,
    context: RequestContext = Depends(require_administrator),
) -> dict[str, Any]:
    """手工发放积分，仅管理员可调用。"""
    service = get_service(request)
    record = service.add_points(body.user_id, body.user_name, body.points, body.source, body.source_detail)
    return {"success": True, "data": {"record": record}, "message": f"已为 {body.user_id} 增加 {body.points} 积分（操作人 {context.user_id}）"}


@router.post("/competition")
async def add_competition_points(
    body: CompetitionPointsRequest,
    request: Request,
    context: RequestContext = Depends(require_administrator),
) -> dict[str, Any]:
    """按获奖等级发放竞赛积分，仅管理员可调用。"""
    service = get_service(request)
    result = service.add_competition_points(body.user_id, body.user_name, body.award_level, body.competition_name)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])
    return {"success": True, "data": result, "message": f"竞赛积分已发放（操作人 {context.user_id}）"}


@router.post("/checkin/{user_id}")
async def add_checkin_points(user_id: str, request: Request, user_name: str = "同学") -> dict[str, Any]:
    """每日打卡加分：服务端保证每个用户每天只加一次。"""
    service = get_service(request)
    today = datetime.now().date().isoformat()
    already = any(
        record.get("source") == "checkin" and str(record.get("created_at", "")).startswith(today)
        for record in service.get_user_records(user_id, limit=200)
    )
    if already:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="今天已经打过卡了，明天再来吧")
    result = service.add_checkin_points(user_id, user_name)
    return {"success": True, "data": result, "message": "打卡积分已添加"}
