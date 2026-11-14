"""Task 3 Skill: dormitory coordination and schedule services."""

from decimal import Decimal

from zhihui_qilu.core.models import AgentRequest, AgentResponse
from zhihui_qilu.dormitory_models import (
    DimensionInput,
    DormInspection,
    DutyAssignment,
    InspectionRecord,
    ScheduleEvent,
    SharedExpense,
)
from zhihui_qilu.dormitory_service import DormitoryService, ScheduleCoordinator, TimetableParser
from zhihui_qilu.skills.base import BaseSkill


class DormitorySkill(BaseSkill):
    """Expose timetable import, transparent AA settlements, and constructive feedback."""

    skill_id = "dormitory"
    display_name = "宿舍生活与行程协同"

    def __init__(self, parser: TimetableParser | None = None, service: DormitoryService | None = None) -> None:
        self._parser = parser or TimetableParser()
        self._service = service or DormitoryService()
        self._coordinator = ScheduleCoordinator()

    async def execute(self, request: AgentRequest) -> AgentResponse:
        """Dispatch the bounded Task 3 operations from typed request payloads."""
        action = str(request.payload.get("action", ""))
        if action == "parse_text_timetable":
            events = self._parser.parse_text(request.text)
            return AgentResponse(success=True, message="课表解析完成", data={"events": [event.model_dump(mode="json") for event in events]})
        if action == "settle_expenses":
            expenses = [SharedExpense.model_validate(item) for item in request.payload.get("expenses", [])]
            settlement = self._service.settle_expenses(expenses)
            return AgentResponse(success=True, message="AA 分摊计算完成", data=settlement.model_dump(mode="json"))
        if action == "improvement_suggestion":
            suggestion = self._service.create_improvement_suggestion(DormInspection.model_validate(request.payload.get("inspection", {})))
            return AgentResponse(success=True, message=suggestion, data={"suggestion": suggestion})
        if action == "analyze_schedule_conflicts":
            assignments = [DutyAssignment.model_validate(item) for item in request.payload.get("assignments", [])]
            member_events = {member: [ScheduleEvent.model_validate(event) for event in events] for member, events in request.payload.get("member_events", {}).items()}
            conflicts = self._coordinator.find_conflicts(assignments, member_events)
            suggestions = self._coordinator.suggest_swaps(conflicts, assignments, member_events)
            return AgentResponse(success=True, message="日程冲突分析完成", data={"conflicts": [item.model_dump(mode="json") for item in conflicts], "suggestions": [item.model_dump(mode="json") for item in suggestions]})

        # 命题二要的「宿舍检查反馈」：五个维度各一句「看到什么 + 怎么改」，不打分不排名
        if action == "inspection_report":
            label = str(request.payload.get("dormitory_label") or "").strip()
            if not label:
                return AgentResponse(success=False, message="先填宿舍号，比如「文渊楼 3-502」")
            try:
                inputs = [DimensionInput.model_validate(item) for item in request.payload.get("dimensions", [])]
            except ValueError as exc:
                return AgentResponse(success=False, message=f"维度数据不对：{exc}")
            report = self._service.build_inspection_report(
                label,
                inputs,
                strengths=[str(item) for item in request.payload.get("strengths", [])],
            )
            return AgentResponse(success=True, message=report.summary, data=report.model_dump(mode="json"))

        # 命题二要的「典型问题汇总」：过半宿舍有的算共性，一两个宿舍有的算个别隐患
        if action == "issue_digest":
            try:
                records = [InspectionRecord.model_validate(item) for item in request.payload.get("records", [])]
            except ValueError as exc:
                return AgentResponse(success=False, message=f"检查记录格式不对：{exc}")
            digest = self._service.summarize_issues(records)
            return AgentResponse(success=True, message=digest.summary, data=digest.model_dump(mode="json"))

        return AgentResponse(success=False, message="不支持的宿舍协同操作", data={"supported_actions": ["parse_text_timetable", "settle_expenses", "improvement_suggestion", "analyze_schedule_conflicts", "inspection_report", "issue_digest"]})
