"""System integration API routes."""

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/integration", tags=["integration"])


class AppointmentRequest(BaseModel):
    student_id: str
    slot_id: str
    reason: str


def get_service(request: Request):
    return request.app.state.container.system_integration


@router.get("/status")
async def get_integration_status(request: Request) -> dict[str, Any]:
    """Get system integration status."""
    return {
        "success": True,
        "data": {
            "sso": {"status": "placeholder", "message": "SSO/JWT接口已预留，等待学校对接"},
            "academic": {"status": "placeholder", "message": "教务系统接口已预留，等待学校API"},
            "psychology": {"status": "placeholder", "message": "心理中心接口已预留，等待学校对接"},
            "student_affairs": {"status": "placeholder", "message": "学工系统接口已预留，等待学校API"},
            "note": "当前所有接口返回模拟数据，接入真实系统后将显示实际数据"
        }
    }


@router.get("/student/{student_id}/dashboard")
async def get_student_dashboard(student_id: str, request: Request) -> dict[str, Any]:
    """Get aggregated student dashboard from all systems."""
    service = get_service(request)
    dashboard = await service.get_student_dashboard(student_id)
    return {"success": True, "data": dashboard}


@router.get("/academic/timetable/{student_id}")
async def get_timetable(student_id: str, request: Request) -> dict[str, Any]:
    """Get student timetable from academic system."""
    service = get_service(request)
    timetable = await service.academic.get_student_timetable(student_id)
    return {"success": True, "data": {"timetable": timetable}}


@router.get("/academic/grades/{student_id}")
async def get_grades(student_id: str, request: Request) -> dict[str, Any]:
    """Get student grades from academic system."""
    service = get_service(request)
    grades = await service.academic.get_student_grades(student_id)
    return {"success": True, "data": {"grades": grades}}


@router.get("/academic/exams/{student_id}")
async def get_exams(student_id: str, request: Request) -> dict[str, Any]:
    """Get exam schedule from academic system."""
    service = get_service(request)
    exams = await service.academic.get_exam_schedule(student_id)
    return {"success": True, "data": {"exams": exams}}


@router.get("/psychology/slots")
async def get_psychology_slots(request: Request) -> dict[str, Any]:
    """Get available psychology counseling slots."""
    service = get_service(request)
    slots = await service.psychology.get_available_slots()
    return {"success": True, "data": {"slots": slots}}


@router.post("/psychology/appointment")
async def create_appointment(body: AppointmentRequest, request: Request) -> dict[str, Any]:
    """Create psychology counseling appointment."""
    service = get_service(request)
    result = await service.psychology.create_appointment(body.student_id, body.slot_id, body.reason)
    return {"success": True, "data": result}


@router.get("/student/{student_id}/info")
async def get_student_info(student_id: str, request: Request) -> dict[str, Any]:
    """Get student basic information."""
    service = get_service(request)
    info = await service.student_affairs.get_student_info(student_id)
    if not info:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="学生信息不存在")
    return {"success": True, "data": info}


@router.get("/student/{student_id}/dormitory")
async def get_dormitory_info(student_id: str, request: Request) -> dict[str, Any]:
    """Get student dormitory information."""
    service = get_service(request)
    info = await service.student_affairs.get_dormitory_info(student_id)
    if not info:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="宿舍信息不存在")
    return {"success": True, "data": info}