"""Task 5 Skill: innovation competitions and unified Campus Points services."""

from zhihui_qilu.core.enums import UserRole
from zhihui_qilu.core.models import AgentRequest, AgentResponse
from zhihui_qilu.innovation_models import CompetitionSubmission, ReviewDecision, StudentSkillProfile, TeamRequirement
from zhihui_qilu.innovation_service import CompetitionReviewHall, ProposalOutlineGenerator, TeamMatcher
from zhihui_qilu.skills.base import BaseSkill


class InnovationSkill(BaseSkill):
    """Expose UGC scoring, administrator review, teaming, and proposal-outline operations."""

    skill_id = "innovation"
    display_name = "双创竞赛孵化与同频成长积分"
    allowed_roles = {UserRole.STUDENT, UserRole.COUNSELOR, UserRole.ADMINISTRATOR}

    def __init__(self, review_hall: CompetitionReviewHall | None = None) -> None:
        self.review_hall = review_hall or CompetitionReviewHall()
        self._matcher = TeamMatcher()
        self._outline_generator = ProposalOutlineGenerator()

    async def execute(self, request: AgentRequest) -> AgentResponse:
        """Dispatch bounded Task 5 operations; the gateway applies role permissions before this point."""
        action = str(request.payload.get("action", ""))
        if action == "submit_competition":
            submission = CompetitionSubmission.model_validate({**request.payload.get("submission", {}), "submitter_id": request.context.user_id})
            scoring = self.review_hall.submit(submission)
            return AgentResponse(success=True, message="竞赛信息已提交审核大厅", data={"submission_id": str(submission.submission_id), "scoring_advice": scoring.model_dump(mode="json")})
        if action == "review_competition":
            if request.context.role != UserRole.ADMINISTRATOR:
                return AgentResponse(success=False, message="仅管理员可执行审核")
            result = self.review_hall.review(str(request.payload["submission_id"]), ReviewDecision.model_validate({**request.payload.get("decision", {}), "reviewer_id": request.context.user_id}))
            return AgentResponse(success=True, message="审核已完成", data=result.model_dump(mode="json"))
        if action == "pending_competitions":
            if request.context.role != UserRole.ADMINISTRATOR:
                return AgentResponse(success=False, message="仅管理员可查看审核大厅")
            return AgentResponse(success=True, message="已获取待审核竞赛", data={"submissions": [item.model_dump(mode="json") for item in self.review_hall.pending()]})
        if action == "match_team":
            requirement = TeamRequirement.model_validate(request.payload.get("requirement", {}))
            profiles = [StudentSkillProfile.model_validate(item) for item in request.payload.get("profiles", [])]
            return AgentResponse(success=True, message="技能向量匹配完成", data={"matches": [item.model_dump() for item in self._matcher.match(requirement, profiles)]})
        if action == "proposal_outline":
            outline = self._outline_generator.generate(str(request.payload["project_name"]), str(request.payload["competition_name"]), list(request.payload.get("technical_keywords", [])))
            return AgentResponse(success=True, message="申报书大纲已生成", data=outline.model_dump())
        return AgentResponse(success=False, message="不支持的双创操作", data={"supported_actions": ["submit_competition", "review_competition", "pending_competitions", "match_team", "proposal_outline"]})
