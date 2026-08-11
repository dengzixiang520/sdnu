"""Task 4 Skill: postgraduate interview simulation and note organization."""

from zhihui_qilu.academic_models import InterviewConfig, TranscriptSegment
from zhihui_qilu.academic_service import AcademicService, NoteOrganizer
from zhihui_qilu.core.models import AgentRequest, AgentResponse
from zhihui_qilu.skills.base import BaseSkill


class AcademicSkill(BaseSkill):
    """Expose bounded, structured Task 4 operations through the central router."""

    skill_id = "academic"
    display_name = "考研复试模拟与笔记整理"

    def __init__(self, service: AcademicService, organizer: NoteOrganizer | None = None) -> None:
        self._service = service
        self._organizer = organizer or NoteOrganizer()

    async def execute(self, request: AgentRequest) -> AgentResponse:
        """Dispatch interview planning, assessment, or transcript organization actions."""
        action = str(request.payload.get("action", ""))
        if action == "start_interview":
            session = self._service.simulator.start(InterviewConfig.model_validate(request.payload.get("config", {})))
            return AgentResponse(success=True, message="复试模拟已创建", data=session.model_dump(mode="json"))
        if action == "evaluate_interview":
            evaluation = await self._service.evaluate_and_remember(request.context.user_id, request.context.session_id, request.text)
            return AgentResponse(success=True, message="五维评估已生成", data=evaluation.model_dump(mode="json"))
        if action == "organize_transcript":
            segments = [TranscriptSegment.model_validate(item) for item in request.payload.get("segments", [])]
            note = self._organizer.organize(segments)
            return AgentResponse(success=True, message="结构化笔记已生成", data=note.model_dump(mode="json"))
        return AgentResponse(success=False, message="不支持的学业成长操作", data={"supported_actions": ["start_interview", "evaluate_interview", "organize_transcript"]})
