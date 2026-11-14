"""定向命题六 Skill：学术海报一键生成。

一次生成 = 排版 + 内容体检。海报不是论文，所以除了排版还要告诉用户
「哪一栏写太长了」「缺结论栏」这类只有做过海报的人才会提醒的事。
"""

from zhihui_qilu.core.models import AgentRequest, AgentResponse
from zhihui_qilu.poster_models import PosterRequest
from zhihui_qilu.poster_service import PosterService
from zhihui_qilu.skills.base import BaseSkill


class PosterSkill(BaseSkill):
    """Expose printable academic poster generation."""

    skill_id = "poster"
    display_name = "学术海报生成"

    def __init__(self, service: PosterService | None = None) -> None:
        self._service = service or PosterService()

    async def execute(self, request: AgentRequest) -> AgentResponse:
        """Build a poster plan from a typed payload."""
        action = str(request.payload.get("action", "")).strip()
        if action not in {"build_poster", "build"}:
            return AgentResponse(
                success=False,
                message="不支持的海报操作",
                data={"supported_actions": ["build_poster"]},
            )

        raw = request.payload.get("poster")
        if not isinstance(raw, dict):
            return AgentResponse(success=False, message="没有收到海报内容，先填标题和栏目")

        try:
            payload = PosterRequest.model_validate(raw)
        except ValueError as exc:
            return AgentResponse(success=False, message=f"海报内容不完整：{exc}")

        if not payload.sections:
            return AgentResponse(success=False, message="至少写一栏内容，比如「结论」")

        plan = self._service.build(payload)
        message = f"已生成 {plan.size_label}，体检通过 {plan.passed_count}/{len(plan.checklist)} 项"
        return AgentResponse(success=True, message=message, data=plan.model_dump(mode="json"))
