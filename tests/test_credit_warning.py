import asyncio

import pytest

from zhihui_qilu.config import Settings
from zhihui_qilu.core.enums import UserRole
from zhihui_qilu.core.models import AgentRequest, RequestContext
from zhihui_qilu.core.security import SecurityIsolationGateway
from zhihui_qilu.credit_service import CreditWarningService
from zhihui_qilu.memory.in_memory import InMemoryMemorySystem
from zhihui_qilu.skills.academic import AcademicSkill
from zhihui_qilu.academic_service import AcademicService
from zhihui_qilu.wellbeing_models import MoodCheckIn, MoodWeather
from zhihui_qilu.wellbeing_service import WellbeingService


def test_annual_credit_shortfall_triggers_warning() -> None:
    """一学年不足 20 学分是学校明文标准，命中即 warning，并给出学生该做的动作。"""
    result = CreditWarningService().assess(
        grade=2, program_years=4, required_credits=160, earned_credits=55, year_credits=14, failed_courses=0
    )
    assert result.level == "warning"
    codes = {item.code for item in result.triggers}
    assert "annual_shortfall" in codes
    assert any("20 学分" in item.detail for item in result.triggers)
    # 学生侧动作里必须提醒先看清触发哪一条，别把提醒当结论
    assert any("哪一条" in step for step in result.student_steps)
    assert len(result.school_steps) == 4


def test_graduation_shortfall_uses_program_year_ratio() -> None:
    """四年制 65%、五年制 70%，同一份学分数据在两种学制下结论可能不同。"""
    four = CreditWarningService().assess(
        grade=4, program_years=4, required_credits=160, earned_credits=100, year_credits=30
    )
    five = CreditWarningService().assess(
        grade=5, program_years=5, required_credits=200, earned_credits=120, year_credits=30
    )
    assert four.level == "warning" and any(item.code == "graduation_shortfall" for item in four.triggers)
    # 100/160=62.5% 低于 65%；120/200=60% 低于 70%，两者都应命中
    assert five.level == "warning" and any(item.code == "graduation_shortfall" for item in five.triggers)
    passed = CreditWarningService().assess(
        grade=4, program_years=4, required_credits=160, earned_credits=120, year_credits=30
    )
    assert passed.level == "ok" and passed.triggers == []


def test_pace_behind_is_marked_as_system_suggestion_not_school_rule() -> None:
    """进度偏慢是我们自己算的参考值，basis 必须写清楚，不能冒充学校标准。"""
    result = CreditWarningService().assess(
        grade=3, program_years=4, required_credits=160, earned_credits=60, year_credits=22
    )
    pace = [item for item in result.triggers if item.code == "pace_behind"]
    assert pace and "不是学校预警标准" in pace[0].basis
    # 只命中系统提醒时等级是 watch，不是 warning
    assert result.level == "watch"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"grade": 2, "program_years": 3, "required_credits": 160, "earned_credits": 10, "year_credits": 10}, "学制"),
        ({"grade": 5, "program_years": 4, "required_credits": 160, "earned_credits": 10, "year_credits": 10}, "学年"),
        ({"grade": 2, "program_years": 4, "required_credits": 0, "earned_credits": 10, "year_credits": 10}, "总学分"),
    ],
)
def test_invalid_credit_input_is_rejected(kwargs: dict, message: str) -> None:
    with pytest.raises(ValueError) as error:
        CreditWarningService().assess(**kwargs)
    assert message in str(error.value)


def test_credit_warning_action_reports_readable_failure() -> None:
    """Skill 层要把非法输入转成一句能照着改的提示，而不是抛 500。"""

    async def exercise() -> None:
        settings = Settings(environment="test")
        service = AcademicService(InMemoryMemorySystem(), settings)
        skill = AcademicSkill(service, settings=settings)
        request = AgentRequest(
            payload={"action": "credit_warning", "grade": 0, "program_years": 4, "required_credits": 160, "earned_credits": 10, "year_credits": 10},
            context=RequestContext(user_id="student-1", session_id="s1", role=UserRole.STUDENT),
        )
        response = await skill.execute(request)
        assert not response.success and "学分数据" in response.message

    asyncio.run(exercise())


def test_self_check_scores_phq2_and_gad2_separately() -> None:
    """PHQ-2 / GAD-2 分别计分：任一 >=3 即建议预约，但不下诊断。"""

    async def exercise() -> None:
        settings = Settings(environment="test")
        service = WellbeingService(InMemoryMemorySystem(), SecurityIsolationGateway(settings), settings)

        calm = await service.submit_self_check("u1", "s1", {"interest": 0, "mood": 0, "anxious": 1, "worry": 0})
        assert calm["level"] == "green" and calm["recommend_booking"] is False

        low = await service.submit_self_check("u1", "s1", {"interest": 1, "mood": 1, "anxious": 0, "worry": 0})
        assert low["level"] == "yellow" and low["phq2"] == 2

        anxious = await service.submit_self_check("u1", "s1", {"interest": 0, "mood": 0, "anxious": 2, "worry": 2})
        assert anxious["level"] == "orange" and anxious["recommend_booking"] is True
        assert anxious["gad2"] == 4 and anxious["phq2"] == 0
        # 提醒里必须带「不是诊断」，且给得出热线
        assert "不是诊断" in str(anxious["disclaimer"])
        assert "12356" in str(anxious["hotline"])

    asyncio.run(exercise())


def test_self_check_rejects_missing_answer() -> None:
    async def exercise() -> None:
        settings = Settings(environment="test")
        service = WellbeingService(InMemoryMemorySystem(), SecurityIsolationGateway(settings), settings)
        with pytest.raises(ValueError):
            await service.submit_self_check("u1", "s1", {"interest": 1})

    asyncio.run(exercise())


def test_growth_note_rotates_by_day_and_follows_alert_level() -> None:
    """导言必须跟着状态选方向：橙/红走情绪管理，绿且没打卡走目标设定。"""

    async def exercise() -> None:
        settings = Settings(environment="test")
        service = WellbeingService(InMemoryMemorySystem(), SecurityIsolationGateway(settings), settings)

        fresh = await service.compose_growth_note("u1")
        assert fresh["tag"] == "目标设定" and fresh["note"]

        for _ in range(5):
            await service.record_check_in("u1", "s1", MoodCheckIn(weather=MoodWeather.RAINY))
        escalated = await service.compose_growth_note("u1")
        assert escalated["tag"] == "情绪管理"
        # 同一句文案不许在四个方向里复用，避免看起来像模板
        pools = service._GROWTH_NOTES
        assert len({note for notes in pools.values() for note in notes}) == sum(len(notes) for notes in pools.values())

    asyncio.run(exercise())
