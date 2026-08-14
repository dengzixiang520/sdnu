"""Points and leaderboard API routes."""

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/points", tags=["points"])


class AddPointsRequest(BaseModel):
    user_id: str
    user_name: str
    points: int
    source: str
    source_detail: str = ""


class CompetitionPointsRequest(BaseModel):
    user_id: str
    user_name: str
    award_level: str
    competition_name: str


def get_service(request: Request):
    return request.app.state.container.points_service


@router.get("/leaderboard")
async def get_leaderboard(request: Request, limit: int = 20) -> dict[str, Any]:
    """Get points leaderboard."""
    service = get_service(request)
    leaderboard = service.get_leaderboard(limit)
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
    records = service.get_user_records(user_id, limit)
    return {"success": True, "data": {"records": records}}


@router.get("/badges")
async def get_badges(request: Request) -> dict[str, Any]:
    """Get all badge definitions."""
    service = get_service(request)
    badges = service.get_badges()
    return {"success": True, "data": {"badges": badges}}


@router.get("/rules")
async def get_points_rules(request: Request) -> dict[str, Any]:
    """Get points rules."""
    service = get_service(request)
    rules = service.get_points_rules()
    return {"success": True, "data": {"rules": rules}}


@router.post("/add")
async def add_points(body: AddPointsRequest, request: Request) -> dict[str, Any]:
    """Add points to user."""
    service = get_service(request)
    record = service.add_points(body.user_id, body.user_name, body.points, body.source, body.source_detail)
    return {"success": True, "data": {"record": record}, "message": f"成功添加{body.points}积分"}


@router.post("/competition")
async def add_competition_points(body: CompetitionPointsRequest, request: Request) -> dict[str, Any]:
    """Add points for competition award."""
    service = get_service(request)
    result = service.add_competition_points(body.user_id, body.user_name, body.award_level, body.competition_name)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])
    return {"success": True, "data": result, "message": "竞赛积分已添加"}


@router.post("/checkin/{user_id}")
async def add_checkin_points(user_id: str, request: Request, user_name: str = "同学") -> dict[str, Any]:
    """Add points for daily check-in."""
    service = get_service(request)
    result = service.add_checkin_points(user_id, user_name)
    return {"success": True, "data": result, "message": "打卡积分已添加"}