import asyncio
from datetime import datetime, timezone

from zhihui_qilu.core.enums import UserRole
from zhihui_qilu.core.models import AgentRequest, RequestContext
from zhihui_qilu.innovation_models import CompetitionSubmission, ReviewDecision, StudentSkillProfile, TeamRequirement
from zhihui_qilu.innovation_service import CompetitionReviewHall, ProposalOutlineGenerator, TeamMatcher
from zhihui_qilu.skills.innovation import InnovationSkill


def submission(submitter: str, **updates: object) -> CompetitionSubmission:
    defaults = {"submitter_id": submitter, "competition_name": "中国国际大学生创新大赛", "edition": "2026", "official_url": "https://www.example.edu/contest", "deadline": datetime(2026, 9, 1, tzinfo=timezone.utc), "eligible_participants": "在校本科生", "official_attachment_uri": "storage://notice.pdf"}
    return CompetitionSubmission(**(defaults | updates))


def test_review_hall_first_release_increment_and_duplicate_are_auditable() -> None:
    hall = CompetitionReviewHall()
    first = submission("u1")
    assert hall.submit(first).points == 10
    first_result = hall.review(str(first.submission_id), ReviewDecision(approved=True, reviewer_id="admin"))
    assert first_result.transaction and hall.ledger.balance_for("u1") == 10
    increment = submission("u2", deadline=datetime(2026, 9, 8, tzinfo=timezone.utc))
    assert hall.submit(increment).points == 2
    assert hall.review(str(increment.submission_id), ReviewDecision(approved=True, reviewer_id="admin")).transaction.points == 2
    duplicate = submission("u3", deadline=datetime(2026, 9, 8, tzinfo=timezone.utc))
    assert hall.submit(duplicate).points == 0
    assert hall.review(str(duplicate.submission_id), ReviewDecision(approved=False, reviewer_id="admin")).transaction is None


def test_team_matching_and_proposal_outline() -> None:
    matches = TeamMatcher().match(TeamRequirement(project_name="校园 AI", required_skills={"python": 1, "frontend": 1}), [StudentSkillProfile(student_id="u1", display_name="小王", skills={"python": 1}), StudentSkillProfile(student_id="u2", display_name="小李", skills={"frontend": 1, "python": 1})])
    assert matches[0].student_id == "u2"
    outline = ProposalOutlineGenerator().generate("校园 AI", "创新大赛", ["FastAPI", "多 Agent"])
    assert "技术路线" in outline.sections[3]


def test_pending_competitions_are_visible_only_to_administrators() -> None:
    """The review queue must never expose student submissions to ordinary users."""
    skill = InnovationSkill()
    skill.review_hall.submit(submission("u1"))

    async def exercise() -> None:
        student_result = await skill.execute(
            AgentRequest(
                payload={"action": "pending_competitions"},
                context=RequestContext(user_id="student-1", session_id="s1", role=UserRole.STUDENT),
            )
        )
        assert student_result.success is False
        assert "submissions" not in student_result.data

        admin_result = await skill.execute(
            AgentRequest(
                payload={"action": "pending_competitions"},
                context=RequestContext(user_id="admin-1", session_id="s2", role=UserRole.ADMINISTRATOR),
            )
        )
        assert admin_result.success is True
        assert len(admin_result.data["submissions"]) == 1
        assert admin_result.data["submissions"][0]["submitter_id"] == "u1"

    asyncio.run(exercise())
