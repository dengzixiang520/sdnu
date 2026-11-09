"""Task 2 Skill: counseling, wellbeing, and warm-space services."""

from zhihui_qilu.core.models import AgentRequest, AgentResponse
from zhihui_qilu.core.enums import UserRole
from zhihui_qilu.skills.base import BaseSkill
from zhihui_qilu.wellbeing_models import HappyShareDraft, MoodCheckIn
from zhihui_qilu.wellbeing_service import HappyShareRejected, WellbeingService


class WellbeingSkill(BaseSkill):
    """Expose explicit, auditable wellbeing actions to the SuperAgentRouter."""

    skill_id = "wellbeing"
    display_name = "辅导员心育与暖心空间"

    def __init__(self, service: WellbeingService) -> None:
        self._service = service

    async def execute(self, request: AgentRequest) -> AgentResponse:
        """Dispatch supported actions without using unbounded agent tool execution."""
        action = str(request.payload.get("action", ""))
        
        # 学生功能
        if action == "greeting":
            greeting = await self._service.create_greeting(request.context.user_id, request.context.session_id)
            return AgentResponse(success=True, message=greeting, data={"greeting": greeting})
        
        if action == "control":
            command = self._service.parse_control_command(request.text)
            return AgentResponse(success=command is not None, message="已生成控制指令" if command else "未识别支持的环境控制指令", data={"command": command.model_dump() if command else None})
        
        if action == "mood_checkin":
            result = await self._service.record_check_in(request.context.user_id, request.context.session_id, MoodCheckIn.model_validate(request.payload.get("check_in", {})))
            return AgentResponse(success=True, message=result.support_message, data=result.model_dump(mode="json"))
        
        if action == "wall_messages":
            messages = await self._service.list_wall_messages()
            return AgentResponse(success=True, message="已获取寄语墙", data={"messages": [message.model_dump(mode="json") for message in messages]})

        # 开心分享墙：公开可见的积极内容，与私密的心情打卡分开
        if action == "happy_shares":
            shares = await self._service.list_happy_shares()
            return AgentResponse(success=True, message="已获取开心分享", data={"shares": [share.model_dump(mode="json") for share in shares]})

        if action == "publish_happy_share":
            draft = HappyShareDraft.model_validate(request.payload.get("share", {}))
            try:
                share = await self._service.publish_happy_share(
                    request.context.user_id,
                    request.context.session_id,
                    str(request.payload.get("author_name") or "同学"),
                    draft,
                )
            except HappyShareRejected as rejection:
                return AgentResponse(success=False, message=rejection.message, data={"redirect": rejection.redirect})
            return AgentResponse(success=True, message="已发布到开心分享墙", data={"share": share.model_dump(mode="json")})

        if action == "cheer_happy_share":
            share = await self._service.cheer_happy_share(str(request.payload.get("share_id", "")))
            if share is None:
                return AgentResponse(success=False, message="这条分享不存在或已下架")
            return AgentResponse(success=True, message="已送出鼓励", data={"share": share.model_dump(mode="json")})
        
        # 辅导员功能
        if action == "publish_wall_message":
            if request.context.role not in {UserRole.COUNSELOR, UserRole.ADMINISTRATOR}:
                return AgentResponse(success=False, message="仅辅导员或管理员可发布寄语")
            from zhihui_qilu.wellbeing_models import WallMessage
            message = await self._service.publish_wall_message(WallMessage.model_validate(request.payload.get("message", {})))
            return AgentResponse(success=True, message="寄语已发布", data=message.model_dump(mode="json"))
        
        if action == "list_alerts":
            if request.context.role not in {UserRole.COUNSELOR, UserRole.ADMINISTRATOR}:
                return AgentResponse(success=False, message="仅辅导员或管理员可查看预警")
            alerts = await self._service.list_counselor_alerts()
            return AgentResponse(success=True, message="已获取预警列表", data={"alerts": alerts})
        
        if action == "create_talk_ledger":
            if request.context.role not in {UserRole.COUNSELOR, UserRole.ADMINISTRATOR}:
                return AgentResponse(success=False, message="仅辅导员或管理员可创建谈心台账")
            from zhihui_qilu.wellbeing_models import TalkLedgerInput
            entry = self._service.build_talk_ledger(TalkLedgerInput.model_validate(request.payload.get("ledger", {})))
            return AgentResponse(success=True, message="谈心记录已创建", data=entry.model_dump(mode="json"))
        
        return AgentResponse(success=False, message="不支持的心育操作", data={
            "student_actions": ["greeting", "control", "mood_checkin", "wall_messages", "happy_shares", "publish_happy_share", "cheer_happy_share"],
            "staff_actions": ["publish_wall_message", "list_alerts", "create_talk_ledger"]
        })