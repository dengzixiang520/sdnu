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
