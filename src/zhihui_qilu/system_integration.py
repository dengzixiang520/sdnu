"""System integration adapters with placeholder implementations."""

from abc import ABC, abstractmethod
from typing import Any
from pydantic import BaseModel


class SSOProvider(ABC):
    """School SSO/JWT authentication adapter interface."""
    
    @abstractmethod
    async def verify_token(self, token: str) -> dict[str, Any] | None:
        """Verify JWT token and return user claims."""
        ...
    
    @abstractmethod
    async def get_user_info(self, user_id: str) -> dict[str, Any] | None:
        """Get user information from SSO system."""
        ...


class AcademicSystemAdapter(ABC):
    """Academic affairs system adapter interface."""
    
    @abstractmethod
    async def get_student_timetable(self, student_id: str) -> list[dict[str, Any]]:
        """Get student's course timetable."""
        ...
    
    @abstractmethod
    async def get_student_grades(self, student_id: str) -> list[dict[str, Any]]:
        """Get student's grades."""
        ...
    
    @abstractmethod
    async def get_exam_schedule(self, student_id: str) -> list[dict[str, Any]]:
        """Get exam schedule."""
        ...


class PsychologyCenterAdapter(ABC):
    """Psychology center system adapter interface."""
    
    @abstractmethod
    async def get_available_slots(self, counselor_id: str | None = None) -> list[dict[str, Any]]:
        """Get available counseling slots."""
        ...
    
    @abstractmethod
    async def create_appointment(self, student_id: str, slot_id: str, reason: str) -> dict[str, Any]:
        """Create counseling appointment."""
        ...
    
    @abstractmethod
    async def get_appointment_history(self, student_id: str) -> list[dict[str, Any]]:
        """Get student's appointment history."""
        ...


class StudentAffairsAdapter(ABC):
    """Student affairs system adapter interface."""
    
    @abstractmethod
    async def get_student_info(self, student_id: str) -> dict[str, Any] | None:
        """Get student basic information."""
        ...
    
    @abstractmethod
    async def get_dormitory_info(self, student_id: str) -> dict[str, Any] | None:
        """Get student's dormitory information."""
        ...
    
    @abstractmethod
    async def get_activity_records(self, student_id: str) -> list[dict[str, Any]]:
        """Get student's activity participation records."""
        ...


# ==================== Placeholder Implementations ====================

class PlaceholderSSOProvider(SSOProvider):
    """Placeholder SSO provider - returns mock data for development."""
    
    async def verify_token(self, token: str) -> dict[str, Any] | None:
        """Mock token verification - always returns valid in dev mode."""
        if token == "dev-token":
            return {"user_id": "dev-user", "role": "student", "name": "Dev User"}
        return None
    
    async def get_user_info(self, user_id: str) -> dict[str, Any] | None:
        """Mock user info - returns placeholder data."""
        return {
            "user_id": user_id,
            "name": "开发测试用户",
            "role": "student",
            "department": "计算机学院",
            "grade": "2024",
            "email": f"{user_id}@sdnu.edu.cn"
        }


class PlaceholderAcademicAdapter(AcademicSystemAdapter):
    """Placeholder academic adapter - returns mock data."""
    
    async def get_student_timetable(self, student_id: str) -> list[dict[str, Any]]:
        return [
            {"course": "高等数学", "time": "周一 8:20-9:55", "location": "A101", "teacher": "张教授"},
            {"course": "数据结构", "time": "周三 14:00-15:35", "location": "B202", "teacher": "李老师"},
        ]
    
    async def get_student_grades(self, student_id: str) -> list[dict[str, Any]]:
        return [
            {"course": "高等数学", "score": 92, "credit": 4, "semester": "2024-1"},
            {"course": "数据结构", "score": 88, "credit": 3, "semester": "2024-1"},
        ]
    
    async def get_exam_schedule(self, student_id: str) -> list[dict[str, Any]]:
        return [
            {"course": "高等数学", "time": "2026-01-10 09:00", "location": "A101", "type": "期末考试"},
        ]


class PlaceholderPsychologyAdapter(PsychologyCenterAdapter):
    """Placeholder psychology center adapter."""
    
    async def get_available_slots(self, counselor_id: str | None = None) -> list[dict[str, Any]]:
        return [
            {"slot_id": "slot-1", "counselor": "王老师", "time": "2026-08-20 14:00", "available": True},
            {"slot_id": "slot-2", "counselor": "李老师", "time": "2026-08-21 10:00", "available": True},
        ]
    
    async def create_appointment(self, student_id: str, slot_id: str, reason: str) -> dict[str, Any]:
        return {"appointment_id": "apt-1", "status": "confirmed", "message": "预约成功"}
    
    async def get_appointment_history(self, student_id: str) -> list[dict[str, Any]]:
        return []


class PlaceholderStudentAffairsAdapter(StudentAffairsAdapter):
    """Placeholder student affairs adapter."""
    
    async def get_student_info(self, student_id: str) -> dict[str, Any] | None:
        return {
            "student_id": student_id,
            "name": "测试学生",
            "department": "计算机学院",
            "major": "人工智能",
            "grade": "2024",
            "class": "智能本2401"
        }
    
    async def get_dormitory_info(self, student_id: str) -> dict[str, Any] | None:
        return {
            "building": "文渊楼",
            "room": "301",
            "roommates": ["张三", "李四", "王五"]
        }
    
    async def get_activity_records(self, student_id: str) -> list[dict[str, Any]]:
        return [
            {"activity": "迎新志愿者", "date": "2024-09-01", "hours": 8},
            {"activity": "编程竞赛", "date": "2024-10-15", "hours": 16},
        ]


class SystemIntegrationService:
    """Unified system integration service."""
    
    def __init__(self) -> None:
        # Initialize with placeholder adapters
        # In production, replace with real implementations
        self.sso: SSOProvider = PlaceholderSSOProvider()
        self.academic: AcademicSystemAdapter = PlaceholderAcademicAdapter()
        self.psychology: PsychologyCenterAdapter = PlaceholderPsychologyAdapter()
        self.student_affairs: StudentAffairsAdapter = PlaceholderStudentAffairsAdapter()
    
    async def get_student_dashboard(self, student_id: str) -> dict[str, Any]:
        """Get aggregated student information from all systems."""
        student_info = await self.student_affairs.get_student_info(student_id)
        dormitory = await self.student_affairs.get_dormitory_info(student_id)
        timetable = await self.academic.get_student_timetable(student_id)
        grades = await self.academic.get_student_grades(student_id)
        activities = await self.student_affairs.get_activity_records(student_id)
        
        return {
            "student": student_info,
            "dormitory": dormitory,
            "timetable": timetable,
            "grades": grades,
            "activities": activities,
            "message": "数据来自占位实现，接入真实系统后将显示实际数据"
        }