"""Data contracts for Campus Points, competition UGC review, and innovation teaming."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from zhihui_qilu.core.models import utc_now


class ReviewStatus(StrEnum):
    """Review states; only approved contributions are allowed to earn points."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ContributionKind(StrEnum):
    """Point-producing contribution classes defined by the Campus Points policy."""

    COMPETITION_UGC = "competition_ugc"
    MOOD_CHECKIN = "mood_checkin"
    INTERVIEW_PRACTICE = "interview_practice"
    NOTE_ORGANIZATION = "note_organization"
    TEAM_FORMATION = "team_formation"
    COMPETITION_RESULT = "competition_result"


class CompetitionSubmission(BaseModel):
    """A user-provided competition record submitted to the review hall."""

    submission_id: UUID = Field(default_factory=uuid4)
    submitter_id: str = Field(min_length=1)
    competition_name: str = Field(min_length=1, max_length=200)
    edition: str = Field(min_length=1, max_length=100)
    official_url: str | None = None
    deadline: datetime | None = None
    eligible_participants: str | None = Field(default=None, max_length=500)
    organizer: str | None = Field(default=None, max_length=200)
    official_attachment_uri: str | None = None
    description: str | None = Field(default=None, max_length=2_000)
    submitted_at: datetime = Field(default_factory=utc_now)
    status: ReviewStatus = ReviewStatus.PENDING
    reviewer_id: str | None = None
    review_note: str | None = None


class ReviewDecision(BaseModel):
    """An administrator's final decision for one UGC submission."""

    approved: bool
    reviewer_id: str = Field(min_length=1)
    note: str = Field(default="", max_length=500)


class ScoringDecision(BaseModel):
    """Transparent recommended score before human approval is finalized."""

    points: int = Field(ge=0)
    category: str
    fingerprint: str
    changed_fields: list[str] = Field(default_factory=list)
    explanation: str


class PointTransaction(BaseModel):
    """Immutable ledger entry recording an approved contribution award."""

    transaction_id: UUID = Field(default_factory=uuid4)
    user_id: str
    points: int = Field(gt=0)
    kind: ContributionKind
    source_id: str
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompetitionReviewResult(BaseModel):
    """Review outcome including whether an approved score was posted to the ledger."""

    submission: CompetitionSubmission
    scoring: ScoringDecision
    transaction: PointTransaction | None = None


class StudentSkillProfile(BaseModel):
    """Long-term skill vector used for transparent candidate ranking."""

    student_id: str
    display_name: str
    skills: dict[str, float] = Field(default_factory=dict)


class TeamRequirement(BaseModel):
    """Desired skill weights for a competition or innovation project."""

    project_name: str
    required_skills: dict[str, float] = Field(min_length=1)
    max_candidates: int = Field(default=5, ge=1, le=20)


class TeamMatch(BaseModel):
    """A ranked candidate with deterministic skill-vector match evidence."""

    student_id: str
    display_name: str
    score: float = Field(ge=0, le=1)
    matched_skills: list[str]


class ProposalOutline(BaseModel):
    """Structured outline for a competition or university innovation proposal."""

    project_name: str
    competition_name: str
    sections: list[str]
