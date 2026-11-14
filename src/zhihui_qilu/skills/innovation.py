"""Task 5 Skill: innovation competitions and unified Campus Points services."""

from typing import Any

from zhihui_qilu.core.enums import UserRole
from zhihui_qilu.core.models import AgentRequest, AgentResponse
from zhihui_qilu.innovation_models import CompetitionSubmission, ReviewDecision, StudentSkillProfile, TeamRequirement
from zhihui_qilu.innovation_service import CompetitionReviewHall, ProposalOutlineGenerator, TeamMatcher
from zhihui_qilu.skills.base import BaseSkill


#: 招募板种子帖。答辩环境没有真实的跨用户帖子库，用固定样本把「队伍在招人」这一侧撑起来；
#: 匹配度不是写死的，由 TeamMatcher 按调用方技能向量实时算。
_RECRUIT_SEEDS: tuple[dict[str, Any], ...] = (
    {
        "post_id": "seed-cd-01",
        "competition": "中国大学生计算机设计大赛",
        "title": "校园导览小程序，缺一个视觉",
        "owner": "李思远 · 计算机 2201",
        "slots": 1,
        "deadline": "2026-11-20",
        "skills": {"视觉设计": 0.9, "前端开发": 0.4},
        "note": "已有算法和前端两人，方向是长清湖校区导览。要会 Figma，能画一套插画风图标。",
    },
    {
        "post_id": "seed-tzb-02",
        "competition": "挑战杯",
        "title": "AI 助农选题，缺数据分析",
        "owner": "王雨桐 · 人工智能 2302",
        "slots": 2,
        "deadline": "2026-11-25",
        "skills": {"数据分析": 0.9, "算法建模": 0.5},
        "note": "调研数据已经收了 1200 份，需要有人做清洗和可视化，会 pandas 就行。",
    },
    {
        "post_id": "seed-lqb-03",
        "competition": "蓝桥杯",
        "title": "组队刷题，冲省一",
        "owner": "陈昱宁 · 软件工程 2203",
        "slots": 2,
        "deadline": "2026-12-05",
        "skills": {"算法建模": 0.8, "前端开发": 0.1},
        "note": "每周三晚上在图书馆四楼固定训练，能坚持到 12 月再联系。",
    },
    {
        "post_id": "seed-mcm-04",
        "competition": "全国大学生数学建模大赛",
        "title": "建模队缺一个会写论文的",
        "owner": "赵一鸣 · 数学 2301",
        "slots": 1,
        "deadline": "2026-11-30",
        "skills": {"文案写作": 0.9, "数据分析": 0.4},
        "note": "我负责建模、另一个同学负责编程，需要第三人写摘要和排版，有 LaTeX 基础优先。",
    },
    {
        "post_id": "seed-cd-05",
        "competition": "中国大学生计算机设计大赛",
        "title": "硬件方向，缺嵌入式",
        "owner": "孙浩然 · 电子 2202",
        "slots": 1,
        "deadline": "2026-12-10",
        "skills": {"硬件嵌入式": 0.9},
        "note": "做的是宿舍用电监测，STM32 + 电流互感器已打样，需要有人接手固件。",
    },
)


class InnovationSkill(BaseSkill):
    """Expose UGC scoring, administrator review, teaming, and proposal-outline operations."""

    skill_id = "innovation"
    display_name = "双创竞赛孵化与同频成长积分"
    allowed_roles = {UserRole.STUDENT, UserRole.COUNSELOR, UserRole.ADMINISTRATOR}

    def __init__(self, review_hall: CompetitionReviewHall | None = None) -> None:
        self.review_hall = review_hall or CompetitionReviewHall()
        self._matcher = TeamMatcher()
        self._outline_generator = ProposalOutlineGenerator()

    @staticmethod
    def _clean_skills(raw: Any) -> dict[str, float]:
        """只接受 0 < 权重 <= 1 的数值，脏数据直接丢弃而不是让整块招募板报错。"""
        skills: dict[str, float] = {}
        if not isinstance(raw, dict):
            return skills
        for key, value in raw.items():
            try:
                score = float(value)
            except (TypeError, ValueError):
                continue
            if 0 < score <= 1:
                skills[str(key)] = score
        return skills

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
        if action == "recruit_board":
            # 反向用一次 TeamMatcher：以「我」为唯一候选人，看我在每条招募的技能要求下能拿多少分
            profile = StudentSkillProfile(
                student_id=request.context.user_id,
                display_name=str(request.payload.get("display_name") or "我"),
                skills=self._clean_skills(request.payload.get("my_skills")),
            )
            posts: list[dict[str, Any]] = []
            for seed in _RECRUIT_SEEDS:
                requirement = TeamRequirement(project_name=seed["title"], required_skills=dict(seed["skills"]), max_candidates=1)
                hits = self._matcher.match(requirement, [profile])
                posts.append({**seed, "match": hits[0].model_dump(mode="json") if hits else None})
            filled = sum(1 for post in posts if post["match"])
            return AgentResponse(success=True, message=f"招募板 {len(posts)} 条，其中 {filled} 条与你的技能有重叠", data={"posts": posts, "has_skills": bool(profile.skills)})
        if action == "proposal_outline":
            outline = self._outline_generator.generate(str(request.payload["project_name"]), str(request.payload["competition_name"]), list(request.payload.get("technical_keywords", [])))
            return AgentResponse(success=True, message="申报书大纲已生成", data=outline.model_dump())
        return AgentResponse(success=False, message="不支持的双创操作", data={"supported_actions": ["submit_competition", "review_competition", "pending_competitions", "match_team", "recruit_board", "proposal_outline"]})
