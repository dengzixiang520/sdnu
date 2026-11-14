"""学生情况一页纸与预警去重的回归测试。

命题一要「学生情况汇总」。这里要证明三件事：
一页纸只给档位次数不给原文、不同档位给不同下一步、同一个学生不会把预警列表刷满。
"""

import asyncio
from datetime import timedelta

import pytest

from zhihui_qilu.config import Settings
from zhihui_qilu.core.enums import AccessScope, MemoryTier, SensitivityLevel
from zhihui_qilu.core.models import utc_now
from zhihui_qilu.core.security import SecurityIsolationGateway
from zhihui_qilu.memory.in_memory import InMemoryMemorySystem
from zhihui_qilu.memory.models import MemoryRecord
from zhihui_qilu.wellbeing_models import CounselorAlert
from zhihui_qilu.wellbeing_service import WellbeingService


def build_service() -> tuple[WellbeingService, InMemoryMemorySystem]:
    settings = Settings()
    memory = InMemoryMemorySystem()
    gateway = SecurityIsolationGateway(settings)
    return WellbeingService(memory, gateway, settings), memory


def push_checkin(memory: InMemoryMemorySystem, student: str, weather: str, reflection: str, at) -> MemoryRecord:
    record = MemoryRecord(
        user_id=student,
        session_id="s",
        tier=MemoryTier.SHORT_TERM,
        category="wellbeing.mood_checkin",
        value={"weather": weather, "checked_at": at.isoformat(), "reflection": reflection},
        access_scope=AccessScope.OWNER,
        sensitivity=SensitivityLevel.SENSITIVE,
        expires_at=at + timedelta(days=7),
    )
    asyncio.run(memory.put(record))
    return record


def test_profile_never_leaks_reflection_text() -> None:
    """打卡正文是学生写给自己的，一页纸上不能出现。"""
    service, memory = build_service()
    secret = "我和室友吵架了不想说"
    push_checkin(memory, "stu-1", "stormy", secret, utc_now())

    profile = asyncio.run(service.compose_student_profile("stu-1"))
    dumped = str(profile)
    assert secret not in dumped
    assert "privacy_note" in profile


def test_profile_counts_checkins_and_picks_level() -> None:
    """5 次负面打卡推到橙档，下一步要跟着档位变。"""
    service, memory = build_service()
    now = utc_now()
    for offset in range(5):
        push_checkin(memory, "stu-2", "stormy", "", now - timedelta(hours=offset))

    profile = asyncio.run(service.compose_student_profile("stu-2"))
    assert profile["alert_level"] == "orange"
    assert profile["mood"]["checkins"] == 5
    assert any("两天内安排一次面谈" in step for step in profile["next_steps"])


def test_green_profile_does_not_invent_work() -> None:
    """绿档不能硬造谈话任务——没有问题本身就是好结果。"""
    service, memory = build_service()
    push_checkin(memory, "stu-3", "sunny", "", utc_now())

    profile = asyncio.run(service.compose_student_profile("stu-3"))
    assert profile["alert_level"] == "green"
    assert any("不需要因为这张纸找学生谈话" in step for step in profile["next_steps"])


def test_unknown_student_returns_empty_sheet_not_error() -> None:
    """查一个没数据的学生也要给一张空表，不能 500。"""
    service, _memory = build_service()
    profile = asyncio.run(service.compose_student_profile("nobody"))
    assert profile["alert_level"] == "green"
    assert profile["mood"]["checkins"] == 0
    assert profile["self_check"] is None


def test_alert_list_collapses_same_student() -> None:
    """同一个学生连打五次卡，预警列表只留最新一条，条数记在 alert_count。"""
    service, memory = build_service()
    now = utc_now()
    for offset in range(5):
        alert = CounselorAlert(student_id="stu-4", level="orange", reason_codes=["five_negative_checkins_within_seven_days"])
        asyncio.run(
            memory.put(
                MemoryRecord(
                    user_id="stu-4",
                    tier=MemoryTier.SHORT_TERM,
                    category="wellbeing.counselor_alert",
                    value=alert.model_dump(mode="json"),
                    access_scope=AccessScope.AUTHORIZED_STAFF,
                    sensitivity=SensitivityLevel.RESTRICTED,
                    created_at=now - timedelta(minutes=offset),
                    expires_at=now + timedelta(days=7),
                )
            )
        )

    alerts = asyncio.run(service.list_counselor_alerts())
    assert len(alerts) == 1
    assert alerts[0]["alert_count"] == 5
    assert alerts[0]["student_id"] == "stu-4"


def test_alert_list_keeps_different_students_apart() -> None:
    """去重只按人合，不能把两个学生合成一条。"""
    service, memory = build_service()
    now = utc_now()
    for student in ("stu-5", "stu-6"):
        alert = CounselorAlert(student_id=student, level="yellow", reason_codes=["three_consecutive_negative_checkins"])
        asyncio.run(
            memory.put(
                MemoryRecord(
                    user_id=student,
                    tier=MemoryTier.SHORT_TERM,
                    category="wellbeing.counselor_alert",
                    value=alert.model_dump(mode="json"),
                    access_scope=AccessScope.AUTHORIZED_STAFF,
                    sensitivity=SensitivityLevel.RESTRICTED,
                    created_at=now,
                    expires_at=now + timedelta(days=7),
                )
            )
        )

    alerts = asyncio.run(service.list_counselor_alerts())
    assert len(alerts) == 2
    assert {item["student_id"] for item in alerts} == {"stu-5", "stu-6"}
