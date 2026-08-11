"""Task 6 Skill: compliant administrative and academic document formatting."""

from zhihui_qilu.core.models import AgentRequest, AgentResponse
from zhihui_qilu.document_service import TemplatePreParser
from zhihui_qilu.skills.base import BaseSkill


class DocumentEngineSkill(BaseSkill):
    """Expose safe in-memory formal-element extraction before any file-rendering workflow."""

    skill_id = "document_engine"
    display_name = "公文与学术文档规范化排版"

    def __init__(self, parser: TemplatePreParser | None = None) -> None:
        self._parser = parser or TemplatePreParser()

    async def execute(self, request: AgentRequest) -> AgentResponse:
        """Extract document elements; controlled file I/O stays in authenticated job workers."""
        action = str(request.payload.get("action", ""))
        if action == "extract_elements":
            elements = self._parser.extract_elements(request.text)
            return AgentResponse(success=True, message="已提取公文要素", data=elements.model_dump())
        return AgentResponse(success=False, message="不支持的文档排版操作", data={"supported_actions": ["extract_elements"]})
