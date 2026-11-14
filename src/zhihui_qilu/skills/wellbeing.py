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

        # 进暖心空间时的主动开场：不走大模型，进页面立刻有话
        if action == "guide_opening":
            opening = await self._service.compose_opening(request.context.user_id)
            return AgentResponse(success=True, message=str(opening["opening"]), data=opening)

        # 心情不好时的具体疏导动作（分三组，每条可跳转到对应板块）
        if action == "soothe_suggestions":
            suggestions = await self._service.compose_soothe(request.context.user_id)
            return AgentResponse(success=True, message="已按最近状态准备疏导建议", data=suggestions)

        # 总览页成长导言：每次进来一句，按状态选方向、按天换文案
        if action == "growth_note":
            note = await self._service.compose_growth_note(request.context.user_id)
            return AgentResponse(success=True, message=str(note["note"]), data=note)

        # 4 题极简自评（PHQ-2 + GAD-2）：题面由后端给，前端不硬编码
        if action == "self_check_items":
            return AgentResponse(success=True, message="已获取自评题目", data=self._service.self_check_items())

        if action == "submit_self_check":
            answers = request.payload.get("answers", {})
            if not isinstance(answers, dict):
                return AgentResponse(success=False, message="答案格式不对")
            try:
                result = await self._service.submit_self_check(request.context.user_id, request.context.session_id, answers)
            except ValueError as exc:
                return AgentResponse(success=False, message=str(exc))
            return AgentResponse(success=True, message=str(result["advice"]), data=result)
        
        if action == "control":
            command = self._service.parse_control_command(request.text)
            return AgentResponse(success=command is not None, message="已生成控制指令" if command else "未识别支持的环境控制指令", data={"command": command.model_dump() if command else None})
        
        if action == "mood_checkin":
            result = await self._service.record_check_in(request.context.user_id, request.context.session_id, MoodCheckIn.model_validate(request.payload.get("check_in", {})))
            return AgentResponse(success=True, message=result.support_message, data=result.model_dump(mode="json"))
        
        # 情绪趋势 / 心情日历：只回给打卡本人，窗口受 7 天保留期限制
        if action == "mood_history":
            try:
                days = int(request.payload.get("days", 7))
            except (TypeError, ValueError):
                days = 7
            items = await self._service.list_check_ins(request.context.user_id, max(1, min(days, 7)))
            return AgentResponse(success=True, message=f"已获取最近 {len(items)} 次心情记录", data={"items": items})

        # 学生主动约谈心：橙/红等级时前端会引导到这里，记录对辅导员可见
        if action == "request_booking":
            slot = str(request.payload.get("slot") or "").strip()
            if not slot:
                return AgentResponse(success=False, message="先选一个可约时段")
            booking = await self._service.request_booking(
                request.context.user_id,
                request.context.session_id,
                slot,
                str(request.payload.get("note") or ""),
                str(request.payload.get("alert_level") or ""),
            )
            return AgentResponse(success=True, message=f"已提交预约申请：{slot}，辅导员会在谈心台账里看到", data={"booking": booking})

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

        if action == "list_bookings":
            if request.context.role not in {UserRole.COUNSELOR, UserRole.ADMINISTRATOR}:
                return AgentResponse(success=False, message="仅辅导员或管理员可查看谈心预约")
            bookings = await self._service.list_bookings()
            return AgentResponse(success=True, message=f"待处理预约 {len(bookings)} 条", data={"bookings": bookings})
        
        if action == "create_talk_ledger":
            if request.context.role not in {UserRole.COUNSELOR, UserRole.ADMINISTRATOR}:
                return AgentResponse(success=False, message="仅辅导员或管理员可创建谈心台账")
            from zhihui_qilu.wellbeing_models import TalkLedgerInput
            entry = self._service.build_talk_ledger(TalkLedgerInput.model_validate(request.payload.get("ledger", {})))
            return AgentResponse(success=True, message="谈心记录已创建", data=entry.model_dump(mode="json"))

        # 学生情况一页纸：命题一要的「学生情况汇总」，只给档位、次数、时间
        if action == "student_profile":
            if request.context.role not in {UserRole.COUNSELOR, UserRole.ADMINISTRATOR}:
                return AgentResponse(success=False, message="仅辅导员或管理员可查看学生情况汇总")
            student_id = str(request.payload.get("student_id") or "").strip()
            if not student_id:
                return AgentResponse(success=False, message="先说要看哪位学生，把学号或用户 ID 填上")
            profile = await self._service.compose_student_profile(student_id)
            return AgentResponse(
                success=True,
                message=f"{student_id}：当前 {profile['alert_level']} 档，共 {len(profile['next_steps'])} 条下一步",
                data=profile,
            )

        return AgentResponse(success=False, message="不支持的心育操作", data={
            "student_actions": ["greeting", "guide_opening", "soothe_suggestions", "growth_note", "self_check_items", "submit_self_check", "control", "mood_checkin", "mood_history", "request_booking", "wall_messages", "happy_shares", "publish_happy_share", "cheer_happy_share"],
            "staff_actions": ["publish_wall_message", "list_alerts", "list_bookings", "create_talk_ledger", "student_profile"]
        })