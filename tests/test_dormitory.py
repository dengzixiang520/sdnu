from datetime import datetime, timezone
from decimal import Decimal

from zhihui_qilu.dormitory_models import DutyAssignment, ScheduleEvent, ScheduleSource, SharedExpense
from zhihui_qilu.dormitory_service import DormitoryService, ScheduleCoordinator, TimetableParser
from zhihui_qilu.skills.dormitory import DormitorySkill
from zhihui_qilu.core.models import AgentRequest, RequestContext


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 9, 1, hour, minute, tzinfo=timezone.utc)


def test_timetable_parses_text_ics_and_csv() -> None:
    parser = TimetableParser()
    text_events = parser.parse_text("2026-09-01 08:00-09:40 高等数学 @ A101")
    assert text_events[0].title == "高等数学"
    ics_events = parser.parse_ics("BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:大学英语\nDTSTART:20260901T100000Z\nDTEND:20260901T114000Z\nEND:VEVENT\nEND:VCALENDAR")
    assert ics_events[0].source == ScheduleSource.ICS
    csv_events = parser.parse_csv("课程名称,开始时间,结束时间,地点\n数据结构,2026-09-01 14:00,2026-09-01 15:40,B202")
    assert csv_events[0].location == "B202"


def test_expense_settlement_is_cent_accurate() -> None:
    result = DormitoryService().settle_expenses([SharedExpense(description="水费", amount=Decimal("10.00"), payer_id="a", participant_ids=["a", "b", "c"])])
    assert result.balances == {"a": Decimal("6.66"), "b": Decimal("-3.33"), "c": Decimal("-3.33")}
    assert sum(item.amount for item in result.transfers) == Decimal("6.66")


def test_conflict_detection_and_swap_suggestion() -> None:
    duty = DutyAssignment(member_id="xiaoming", starts_at=at(19), ends_at=at(20))
    schedules = {"xiaoming": [ScheduleEvent(title="组会", starts_at=at(19, 30), ends_at=at(21), source=ScheduleSource.TEXT)], "xiaohua": []}
    coordinator = ScheduleCoordinator()
    conflicts = coordinator.find_conflicts([duty, DutyAssignment(member_id="xiaohua", starts_at=at(20), ends_at=at(21))], schedules)
    suggestions = coordinator.suggest_swaps(conflicts, [duty, DutyAssignment(member_id="xiaohua", starts_at=at(20), ends_at=at(21))], schedules)
    assert conflicts[0].conflicting_event.title == "组会"
    assert suggestions[0].suggested_member_id == "xiaohua"


def test_dormitory_skill_exposes_conflict_analysis() -> None:
    import asyncio
    async def exercise() -> None:
        result = await DormitorySkill().execute(AgentRequest(payload={"action": "analyze_schedule_conflicts", "assignments": [{"member_id": "u1", "starts_at": at(19).isoformat(), "ends_at": at(20).isoformat()}], "member_events": {"u1": [{"title": "组会", "starts_at": at(19, 30).isoformat(), "ends_at": at(20, 30).isoformat(), "source": "text"}]}}, context=RequestContext(user_id="u1", session_id="s1")))
        assert result.success and len(result.data["conflicts"]) == 1
    asyncio.run(exercise())
