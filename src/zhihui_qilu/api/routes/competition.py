"""Competition management API routes."""

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/competitions", tags=["competitions"])


class CompetitionCreate(BaseModel):
    """Request body for creating a competition."""
    name: str
    category: str
    level: str = "国家级"
    organizer: str = ""
    website: str = ""
    description: str = ""
    teamSize: str = "个人"
    time: str = ""
    registrationDeadline: str = ""
    difficulty: str = "中"
    skills: list[str] = Field(default_factory=list)
    awards: list[str] = Field(default_factory=list)
    tips: str = ""


class CompetitionUpdate(BaseModel):
    """Request body for updating a competition."""
    name: str | None = None
    category: str | None = None
    level: str | None = None
    organizer: str | None = None
    website: str | None = None
    description: str | None = None
    teamSize: str | None = None
    time: str | None = None
    registrationDeadline: str | None = None
    difficulty: str | None = None
    skills: list[str] | None = None
    awards: list[str] | None = None
    tips: str | None = None
    isActive: bool | None = None


def get_service(request: Request):
    """Get competition service from app state."""
    return request.app.state.container.competition_service


@router.get("")
async def list_competitions(
    request: Request,
    category: str | None = None,
    keyword: str | None = None,
) -> dict[str, Any]:
    """List all competitions with optional filtering."""
    service = get_service(request)
    
    if keyword:
        competitions = service.search(keyword)
    elif category:
        competitions = service.get_by_category(category)
    else:
        competitions = service.get_all()
    
    categories = service.get_categories()
    
    return {
        "success": True,
        "data": {
            "competitions": competitions,
            "categories": categories,
            "total": len(competitions),
        }
    }


@router.get("/categories")
async def list_categories(request: Request) -> dict[str, Any]:
    """List all competition categories."""
    service = get_service(request)
    categories = service.get_categories()
    return {"success": True, "data": {"categories": categories}}


@router.get("/{competition_id}")
async def get_competition(competition_id: str, request: Request) -> dict[str, Any]:
    """Get a competition by ID."""
    service = get_service(request)
    competition = service.get_by_id(competition_id)
    
    if not competition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="竞赛不存在"
        )
    
    return {"success": True, "data": competition}


@router.post("")
async def create_competition(body: CompetitionCreate, request: Request) -> dict[str, Any]:
    """Create a new competition."""
    service = get_service(request)
    competition = service.create(body.model_dump())
    return {"success": True, "data": competition, "message": "竞赛创建成功"}


@router.put("/{competition_id}")
async def update_competition(
    competition_id: str,
    body: CompetitionUpdate,
    request: Request,
) -> dict[str, Any]:
    """Update an existing competition."""
    service = get_service(request)
    
    update_data = {k: v for k, v in body.model_dump().items() if v is not None}
    competition = service.update(competition_id, update_data)
    
    if not competition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="竞赛不存在"
        )
    
    return {"success": True, "data": competition, "message": "竞赛更新成功"}


@router.delete("/{competition_id}")
async def delete_competition(competition_id: str, request: Request) -> dict[str, Any]:
    """Delete a competition."""
    service = get_service(request)
    
    if not service.delete(competition_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="竞赛不存在"
        )
    
    return {"success": True, "message": "竞赛删除成功"}


@router.post("/import")
async def import_competitions(request: Request) -> dict[str, Any]:
    """Import competitions from the default data file."""
    service = get_service(request)
    imported = service.import_from_json("./data/competitions.json")
    return {
        "success": True,
        "data": {"imported": imported},
        "message": f"成功导入 {imported} 个竞赛"
    }