"""Data contracts for dormitory life, timetable import, and schedule coordination."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class ScheduleSource(StrEnum):
    """Supported source channels for timetable and itinerary information."""

    ICS = "ics"
    SPREADSHEET = "spreadsheet"
    OCR = "ocr"
    TEXT = "text"


class ScheduleEvent(BaseModel):
    """A normalized, timezone-aware activity interval."""

    event_id: UUID = Field(default_factory=uuid4)
    title: str = Field(min_length=1, max_length=200)
    starts_at: datetime
    ends_at: datetime
    location: str | None = Field(default=None, max_length=200)
    source: ScheduleSource

    @field_validator("ends_at")
    @classmethod
    def end_must_follow_start(cls, end: datetime, info: object) -> datetime:
        """Reject malformed intervals before they enter conflict calculations."""
        start = getattr(info, "data", {}).get("starts_at")
        if start is not None and end <= start:
            raise ValueError("ends_at must be later than starts_at")
        return end


class SharedExpense(BaseModel):
    """One confirmed dormitory expense awaiting equitable settlement."""

    expense_id: UUID = Field(default_factory=uuid4)
    description: str = Field(min_length=1, max_length=200)
    amount: Decimal = Field(gt=0, decimal_places=2)
    payer_id: str = Field(min_length=1)
    participant_ids: list[str] = Field(min_length=1)

    @field_validator("participant_ids")
    @classmethod
    def participants_must_be_unique(cls, members: list[str]) -> list[str]:
        if len(members) != len(set(members)):
            raise ValueError("participant_ids must not contain duplicates")
        return members


class SettlementTransfer(BaseModel):
    """A suggested transfer needed to settle an AA ledger."""

    from_member_id: str
    to_member_id: str
    amount: Decimal = Field(gt=0, decimal_places=2)


class ExpenseSettlement(BaseModel):
    """Per-member balances and minimal payment transfer suggestions."""

    balances: dict[str, Decimal]
    transfers: list[SettlementTransfer]


class DormInspection(BaseModel):
    """Observed condition used only to generate constructive, non-shaming feedback."""

    dormitory_label: str = Field(min_length=1, max_length=100)
    observations: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)


class DutyAssignment(BaseModel):
    """A member's assigned shared duty period."""

    member_id: str
    starts_at: datetime
    ends_at: datetime
    duty_name: str = "宿舍值日"

    @field_validator("ends_at")
    @classmethod
    def duty_end_must_follow_start(cls, end: datetime, info: object) -> datetime:
        start = getattr(info, "data", {}).get("starts_at")
        if start is not None and end <= start:
            raise ValueError("ends_at must be later than starts_at")
        return end


class ScheduleConflict(BaseModel):
    """An overlap discovered between a duty and another required activity."""

    member_id: str
    duty: DutyAssignment
    conflicting_event: ScheduleEvent


class SwapSuggestion(BaseModel):
    """A non-binding candidate to discuss before a roster change is finalized."""

    original_member_id: str
    suggested_member_id: str
    duty: DutyAssignment
    rationale: str


class InspectionDimension(StrEnum):
    """定向命题二点名的五类内容：卫生、安全秩序、作息规律、关系调适、文明习惯。"""

    HYGIENE = "hygiene"
    SAFETY = "safety"
    SCHEDULE = "schedule"
    RELATION = "relation"
    CIVILITY = "civility"


class DimensionState(StrEnum):
    """一个维度的现场判断，只用三档，避免变成打分表。"""

    GOOD = "good"
    WATCH = "watch"
    ISSUE = "issue"


class DimensionInput(BaseModel):
    """辅导员对某一个维度的现场观察。"""

    dimension: InspectionDimension
    state: DimensionState = DimensionState.GOOD
    note: str = Field(default="", max_length=200)


class DimensionNote(BaseModel):
    """一个维度的反馈：先说看到什么，再说建议做什么，最后给一句肯定。"""

    dimension: InspectionDimension
    label: str
    state: DimensionState
    observation: str
    feedback: str
    action: str


class InspectionReport(BaseModel):
    """结构化检查反馈。刻意不打分排名，只给「这一项怎么改」。"""

    dormitory_label: str
    notes: list[DimensionNote]
    strengths: list[str]
    summary: str
    encouragement: str
    issue_count: int
    watch_count: int


class InspectionRecord(BaseModel):
    """一次检查的压缩记录，供跨次汇总用。"""

    dormitory_label: str
    dimensions: dict[str, str] = Field(default_factory=dict)


class CommonIssue(BaseModel):
    """共性问题与个别隐患共用同一个形状，靠 ``is_common`` 区分。"""

    dimension: InspectionDimension
    label: str
    dorms: int
    total_dorms: int
    share: int
    advice: str
    is_common: bool


class IssueDigest(BaseModel):
    """跨多次检查的汇总：哪些是共性问题，哪些只是个别隐患。"""

    total_inspections: int
    total_dorms: int
    common_issues: list[CommonIssue]
    isolated_issues: list[CommonIssue]
    summary: str
    note: str
