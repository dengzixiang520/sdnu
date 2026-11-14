"""Task 6 Skill: compliant administrative and academic document formatting."""

from zhihui_qilu.ai.provider import LanguageModelProvider, OfflineProvider
from zhihui_qilu.core.models import AgentRequest, AgentResponse
from zhihui_qilu.document_drafting import compose_draft
from zhihui_qilu.document_phrases import phrase_payload
from zhihui_qilu.document_service import TemplatePreParser
from zhihui_qilu.skills.base import BaseSkill


class DocumentEngineSkill(BaseSkill):
    """Expose safe in-memory formal-element extraction and draft composition."""

    skill_id = "document_engine"
    display_name = "公文与学术文档规范化排版"

    def __init__(self, parser: TemplatePreParser | None = None, provider: LanguageModelProvider | None = None) -> None:
        self._parser = parser or TemplatePreParser()
        self._provider = provider or OfflineProvider()

    async def execute(self, request: AgentRequest) -> AgentResponse:
        """Extract document elements or draft one; file I/O stays in authenticated job workers."""
        action = str(request.payload.get("action", ""))
        if action == "extract_elements":
            elements = self._parser.extract_elements(request.text)
            return AgentResponse(success=True, message="已提取公文要素", data=elements.model_dump())
        if action == "compose_draft":
            doc_type = str(request.payload.get("doc_type") or "notice")
            try:
                draft, source = await compose_draft(self._provider, request.text, doc_type)
            except ValueError as error:
                return AgentResponse(success=False, message=str(error), data={"doc_type": doc_type})
            message = (
                "已按《山东师范大学行政文件格式细则》起草，正文里的 ×× 需要你补实"
                if source == "deepseek"
                else "模型当前不可用，已生成符合细则的结构骨架，按 ×× 占位填空即可"
            )
            return AgentResponse(success=True, message=message, data={"draft": draft, "source": source, "doc_type": doc_type})
        if action == "phrase_book":
            return AgentResponse(success=True, message="已返回公文句式与文种指引", data=phrase_payload())
        return AgentResponse(
            success=False,
            message="不支持的文档排版操作",
            data={"supported_actions": ["extract_elements", "compose_draft", "phrase_book"]},
        )
