import asyncio
from datetime import timedelta

from zhihui_qilu.config import Settings
from zhihui_qilu.core.enums import AccessScope, MemoryTier
from zhihui_qilu.core.models import utc_now
from zhihui_qilu.core.security import SecurityIsolationGateway
from zhihui_qilu.memory.in_memory import InMemoryMemorySystem
from zhihui_qilu.wellbeing_models import AlertLevel, MoodCheckIn, MoodWeather, TalkLedgerInput, WallMessage
from zhihui_qilu.wellbeing_service import WellbeingService
from zhihui_qilu.skills.wellbeing import WellbeingSkill
from zhihui_qilu.core.models import AgentRequest, RequestContext
from zhihui_qilu.core.enums import UserRole


def test_checkin_alerts_and_staff_privacy_boundary() -> None:
    asyncio.run(_exercise_checkins())


async def _exercise_checkins() -> None:
    memory = InMemoryMemorySystem()
    settings = Settings(environment="test")
    service = WellbeingService(memory, SecurityIsolationGateway(settings), settings)
    for day in range(3):
        result = await service.record_check_in("student-1", "session", MoodCheckIn(weather=MoodWeather.RAINY, checked_at=utc_now() - timedelta(days=2 - day)))
    assert result.alert_level == AlertLevel.YELLOW
    red = await service.record_check_in("student-1", "session", MoodCheckIn(weather=MoodWeather.STORMY, reflection="我有自残的想法"))
    assert red.alert_level == AlertLevel.RED and red.human_follow_up_requested
    staff_records = await memory.query(user_id="student-1", tier=MemoryTier.SHORT_TERM, permitted_scopes={AccessScope.AUTHORIZED_STAFF})
    assert staff_records and "reflection" not in str(staff_records[0].value)


def test_five_negative_checkins_escalate_to_orange() -> None:
    asyncio.run(_exercise_orange_threshold())


async def _exercise_orange_threshold() -> None:
    memory = InMemoryMemorySystem()
    settings = Settings(environment="test")
    service = WellbeingService(memory, SecurityIsolationGateway(settings), settings)
    for day in range(5):
        result = await service.record_check_in("student-2", "session", MoodCheckIn(weather=MoodWeather.STORMY, checked_at=utc_now() - timedelta(days=4 - day)))
    assert result.alert_level == AlertLevel.ORANGE


def test_guide_controls_and_ledger() -> None:
    service = WellbeingService(InMemoryMemorySystem(), SecurityIsolationGateway(Settings()), Settings())
    assert service.parse_control_command("请播放舒缓的雨声").track == "rain"
    ledger = service.build_talk_ledger(TalkLedgerInput(student_id="u1", counselor_name="王老师", meeting_at=utc_now(), location="谈心室", topics=["适应大学生活"], agreed_actions=["一周后回访"]))
    assert ledger.archive_status == "draft_for_counselor_review"
    asyncio.run(service.publish_wall_message(WallMessage(content="愿你今天也能照顾好自己。")))
    assert asyncio.run(service.list_wall_messages())[0].content.startswith("愿你")


def test_wall_publish_requires_staff_role() -> None:
    async def exercise() -> None:
        settings = Settings(environment="test")
        skill = WellbeingSkill(WellbeingService(InMemoryMemorySystem(), SecurityIsolationGateway(settings), settings))
        request = AgentRequest(payload={"action": "publish_wall_message", "message": {"content": "你做得很好。"}}, context=RequestContext(user_id="u1", session_id="s1", role=UserRole.STUDENT))
        assert not (await skill.execute(request)).success
        staff_request = request.model_copy(update={"context": request.context.model_copy(update={"role": UserRole.COUNSELOR})})
        assert (await skill.execute(staff_request)).success
    asyncio.run(exercise())
