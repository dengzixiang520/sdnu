"""Task 5 services for auditable points, UGC review, and innovation team formation."""

import hashlib
import math
import re
from collections import defaultdict
from copy import deepcopy
from urllib.parse import urlparse

from zhihui_qilu.innovation_models import (
    CompetitionReviewResult,
    CompetitionSubmission,
    ContributionKind,
    PointTransaction,
    ProposalOutline,
    ReviewDecision,
    ReviewStatus,
    ScoringDecision,
    StudentSkillProfile,
    TeamMatch,
    TeamRequirement,
)


class CampusPointsLedger:
    """Append-only in-memory reference ledger; production adapters should persist transactions."""

    def __init__(self) -> None:
        self._transactions: list[PointTransaction] = []
        self._source_index: dict[str, PointTransaction] = {}

    def post(self, transaction: PointTransaction) -> PointTransaction:
        """Post an idempotent approved contribution; the same source can never award twice."""
        existing = self._source_index.get(transaction.source_id)
        if existing is not None:
            return existing
        self._transactions.append(transaction)
        self._source_index[transaction.source_id] = transaction
        return transaction

    def balance_for(self, user_id: str) -> int:
        """Return the unified balance across all platform contribution sources."""
        return sum(transaction.points for transaction in self._transactions if transaction.user_id == user_id)

    def transactions_for(self, user_id: str) -> list[PointTransaction]:
        """Return the user's chronological audit trail."""
        return [transaction for transaction in self._transactions if transaction.user_id == user_id]


class CompetitionFingerprint:
    """Create stable competition identity hashes from normalized name, edition, and official domain."""

    def __init__(self, aliases: dict[str, str] | None = None) -> None:
        self._aliases = {self._normalize_name(key): self._normalize_name(value) for key, value in (aliases or {}).items()}

    def create(self, submission: CompetitionSubmission) -> str:
        """Hash canonical identity fields; mutable details such as deadlines remain diffable fields."""
        name = self._aliases.get(self._normalize_name(submission.competition_name), self._normalize_name(submission.competition_name))
        domain = urlparse(submission.official_url or "").netloc.lower().removeprefix("www.") or "unknown-domain"
        payload = "|".join((name, self._normalize_name(submission.edition), domain))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize_name(value: str) -> str:
        return re.sub(r"[^\w\u4e00-\u9fff]", "", value).lower()


class CompetitionScorer:
    """Apply first-release decay using hashes and field-level value differences."""

    _COMPLETE_FIELDS = ("competition_name", "official_url", "deadline", "eligible_participants", "official_attachment_uri")
    _KEY_FIELDS = ("official_url", "deadline", "eligible_participants", "official_attachment_uri")

    def score(self, submission: CompetitionSubmission, fingerprint: str, existing: CompetitionSubmission | None) -> ScoringDecision:
        """Recommend 10/5/2-per-key-field/1/0 points without making the final approval decision."""
        if existing is None:
            is_complete = all(getattr(submission, field) not in (None, "") for field in self._COMPLETE_FIELDS)
            return ScoringDecision(points=10 if is_complete else 5, category="first_complete" if is_complete else "first_partial", fingerprint=fingerprint, explanation="首次提交该竞赛，按五要素完整度计算。")
        changed = self._changed_fields(existing, submission)
        key_changes = [field for field in changed if field in self._KEY_FIELDS]
        if key_changes:
            counted = key_changes[:3]
            return ScoringDecision(points=len(counted) * 2, category="key_increment", fingerprint=fingerprint, changed_fields=counted, explanation="已存在同一竞赛，新增或更新关键字段，按每项 2 分、最多计 3 项。")
        if changed:
            return ScoringDecision(points=1, category="minor_increment", fingerprint=fingerprint, changed_fields=changed, explanation="已存在同一竞赛，仅补充非关键说明信息。")
        return ScoringDecision(points=0, category="duplicate", fingerprint=fingerprint, explanation="与已收录信息实质重复，建议驳回且不计入贡献。")

    @staticmethod
    def _changed_fields(existing: CompetitionSubmission, incoming: CompetitionSubmission) -> list[str]:
        fields = ("official_url", "deadline", "eligible_participants", "organizer", "official_attachment_uri", "description")
        return [field for field in fields if getattr(incoming, field) not in (None, "") and getattr(incoming, field) != getattr(existing, field)]


class CompetitionReviewHall:
    """Admin-gated UGC workflow; AI scoring is advisory and never posts points before approval."""

    def __init__(self, ledger: CampusPointsLedger | None = None, fingerprint: CompetitionFingerprint | None = None, scorer: CompetitionScorer | None = None) -> None:
        self.ledger = ledger or CampusPointsLedger()
        self._fingerprint = fingerprint or CompetitionFingerprint()
        self._scorer = scorer or CompetitionScorer()
        self._submissions: dict[str, CompetitionSubmission] = {}
        self._catalog: dict[str, CompetitionSubmission] = {}

    def submit(self, submission: CompetitionSubmission) -> ScoringDecision:
        """Accept a pending submission and return an advisory scoring decision for the review hall."""
        fingerprint = self._fingerprint.create(submission)
        self._submissions[str(submission.submission_id)] = submission
        return self._scorer.score(submission, fingerprint, self._catalog.get(fingerprint))

    def pending(self) -> list[CompetitionSubmission]:
        """List submissions awaiting human review, newest first."""
        return sorted((item for item in self._submissions.values() if item.status == ReviewStatus.PENDING), key=lambda item: item.submitted_at, reverse=True)

    def review(self, submission_id: str, decision: ReviewDecision) -> CompetitionReviewResult:
        """Approve/reject once; approved nonzero contributions receive an immutable ledger entry."""
        submission = self._submissions.get(submission_id)
        if submission is None:
            raise KeyError("Submission was not found")
        if submission.status != ReviewStatus.PENDING:
            raise ValueError("A submission may be reviewed only once")
        fingerprint = self._fingerprint.create(submission)
        scoring = self._scorer.score(submission, fingerprint, self._catalog.get(fingerprint))
        reviewed = submission.model_copy(update={"status": ReviewStatus.APPROVED if decision.approved else ReviewStatus.REJECTED, "reviewer_id": decision.reviewer_id, "review_note": decision.note})
        self._submissions[submission_id] = reviewed
        if not decision.approved:
            return CompetitionReviewResult(submission=reviewed, scoring=scoring)
        self._catalog[fingerprint] = self._merge_catalog(self._catalog.get(fingerprint), reviewed)
        transaction = None
        if scoring.points > 0:
            transaction = self.ledger.post(PointTransaction(user_id=reviewed.submitter_id, points=scoring.points, kind=ContributionKind.COMPETITION_UGC, source_id=f"competition-review:{reviewed.submission_id}", metadata={"fingerprint": fingerprint, "category": scoring.category, "changed_fields": scoring.changed_fields}))
        return CompetitionReviewResult(submission=reviewed, scoring=scoring, transaction=transaction)

    @staticmethod
    def _merge_catalog(existing: CompetitionSubmission | None, incoming: CompetitionSubmission) -> CompetitionSubmission:
        if existing is None:
            return incoming
        updates = {field: getattr(incoming, field) for field in CompetitionScorer._KEY_FIELDS + ("organizer", "description") if getattr(incoming, field) not in (None, "")}
        return existing.model_copy(update=updates)


class TeamMatcher:
    """Rank opt-in student profiles by cosine similarity against an explicit project skill vector."""

    def match(self, requirement: TeamRequirement, candidates: list[StudentSkillProfile]) -> list[TeamMatch]:
        """Return only candidates with positive overlap, ranked deterministically by score then name."""
        matches: list[TeamMatch] = []
        for candidate in candidates:
            score = self._cosine(requirement.required_skills, candidate.skills)
            overlap = sorted(skill for skill in requirement.required_skills if candidate.skills.get(skill, 0) > 0)
            if score > 0:
                matches.append(TeamMatch(student_id=candidate.student_id, display_name=candidate.display_name, score=round(score, 4), matched_skills=overlap))
        return sorted(matches, key=lambda item: (-item.score, item.display_name))[: requirement.max_candidates]

    @staticmethod
    def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
        dot = sum(left.get(key, 0.0) * right.get(key, 0.0) for key in set(left) | set(right))
        left_norm = math.sqrt(sum(value * value for value in left.values()))
        right_norm = math.sqrt(sum(value * value for value in right.values()))
        return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


class ProposalOutlineGenerator:
    """Generate a stable proposal skeleton that users enrich with verified project evidence."""

    def generate(self, project_name: str, competition_name: str, technical_keywords: list[str]) -> ProposalOutline:
        """Return competition-agnostic sections while preserving the caller's project information."""
        stack = "、".join(technical_keywords) if technical_keywords else "待论证的核心技术"
        return ProposalOutline(project_name=project_name, competition_name=competition_name, sections=["一、项目摘要", "二、问题背景与用户需求", "三、方案目标与创新点", f"四、技术路线（{stack}）", "五、系统设计与验证方案", "六、团队分工与实施进度", "七、风险、合规与数据保护", "八、预期成果与推广价值"])
