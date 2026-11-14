"""情绪趋势的回归测试。

单次打卡只能说明当天状态，跨天连起来才是信号。这里钉住四件事：
走低能识别、好转能识别、持平不乱报警、没数据不编造。
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
from zhihui_qilu.wellbeing_service import WellbeingService


def build() -> tuple[WellbeingService, InMemoryMemorySystem]:
    settings = Settings()
    memory = InMemoryMemorySystem()
    return WellbeingService(memory, SecurityIsolationGateway(settings), settings), memory


def push(memory: InMemoryMemorySystem, user: str, weather: str, days_ago: int) -> None:
    at = utc_now() - timedelta(days=days_ago)
    asyncio.run(
        memory.put(
            MemoryRecord(
                user_id=user,
                session_id="s",
                tier=MemoryTier.SHORT_TERM,
                category="wellbeing.mood_checkin",
                value={"weather": weather, "checked_at": at.isoformat(), "reflection": ""},
                access_scope=AccessScope.OWNER,
                sensitivity=SensitivityLevel.SENSITIVE,
                expires_at=at + timedelta(days=7),
            )
        )
    )


def test_no_records_is_honest() -> None:
    """没有打卡就直说，不给趋势结论。"""
    service, _memory = build()
    trend = asyncio.run(service.compose_mood_trend("nobody"))
    assert trend["trend"] == "none"
    assert trend["checkins"] == 0
    assert "还没有打卡记录" in trend["message"]


def test_declining_is_detected() -> None:
    """前两天晴、后几天暴雨，趋势要判成走低。"""
    service, memory = build()
    push(memory, "u1", "sunny", 4)
    push(memory, "u1", "sunny", 3)
    push(memory, "u1", "stormy", 1)
    push(memory, "u1", "stormy", 0)

    trend = asyncio.run(service.compose_mood_trend("u1"))
    assert trend["trend"] == "declining"
    assert trend["trend_label"] == "在走低"
    assert trend["declining_days"] >= 1
    assert "连着往下走" in trend["message"]


def test_improving_is_detected() -> None:
    """反过来要判成好转，不能一直报走低。"""
    service, memory = build()
    push(memory, "u2", "stormy", 4)
    push(memory, "u2", "rainy", 3)
    push(memory, "u2", "sunny", 1)
    push(memory, "u2", "sunny", 0)

    trend = asyncio.run(service.compose_mood_trend("u2"))
    assert trend["trend"] == "improving"
    assert trend["trend_label"] == "在好转"


def test_flat_days_stay_stable() -> None:
    """一直差不多就别说人家在走低。"""
    service, memory = build()
    for offset in range(4):
        push(memory, "u3", "cloudy", offset)

    trend = asyncio.run(service.compose_mood_trend("u3"))
    assert trend["trend"] == "stable"
    assert trend["trend_label"] in {"基本持平", "还不够判断"}


def test_daily_series_is_ordered() -> None:
    """每日序列按日期正序，前端画图直接能用。"""
    service, memory = build()
    push(memory, "u4", "sunny", 2)
    push(memory, "u4", "rainy", 1)
    push(memory, "u4", "stormy", 0)

    trend = asyncio.run(service.compose_mood_trend("u4"))
    days = [item["day"] for item in trend["daily"]]
    assert days == sorted(days)
    assert trend["checkins"] == 3


def test_advice_is_actionable_not_generic() -> None:
    """走低时给的动作要具体到「做什么」，不是「加油」。"""
    service, memory = build()
    push(memory, "u5", "sunny", 3)
    push(memory, "u5", "stormy", 0)

    trend = asyncio.run(service.compose_mood_trend("u5"))
    advice = " ".join(trend["advice"])
    assert advice
    for banned in ("加油", "你可以的", "想开点", "别难过"):
        assert banned not in advice
