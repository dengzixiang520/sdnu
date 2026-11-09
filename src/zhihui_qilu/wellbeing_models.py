"""Privacy-preserving data contracts for the wellbeing and warm-space module."""

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from zhihui_qilu.core.models import utc_now


class MoodWeather(StrEnum):
    """Non-clinical mood choices displayed by the daily check-in UI."""

    SUNNY = "sunny"
    CLOUDY = "cloudy"
    RAINY = "rainy"
    STORMY = "stormy"


class AlertLevel(StrEnum):
    """Support escalation levels defined by the project white paper."""

    GREEN = "green"
    YELLOW = "yellow"
    ORANGE = "orange"
    RED = "red"


class AmbientTrack(StrEnum):
    """Available low-stimulation ambient audio scenes."""

    RAIN = "rain"
    PIANO = "piano"
    FOREST = "forest"


class GuideControlCommand(BaseModel):
    """A client-side control instruction emitted by the warm guide."""

    command: Literal["play_audio", "stop_audio", "set_volume"]
    track: AmbientTrack | None = None
    volume: int | None = Field(default=None, ge=0, le=100)


class MoodCheckIn(BaseModel):
    """Student-submitted daily reflection; free text is never included in staff alerts."""

    weather: MoodWeather
    reflection: str = Field(default="", max_length=2_000)
    checked_at: datetime = Field(default_factory=utc_now)


class MoodCheckInResult(BaseModel):
    """A safe student response after a check-in is recorded."""

    alert_level: AlertLevel
    support_message: str
    booking_suggested: bool = False
    human_follow_up_requested: bool = False


class CounselorAlert(BaseModel):
    """Minimal counselor signal, intentionally excluding chat and reflection source text."""

    alert_id: UUID = Field(default_factory=uuid4)
    student_id: str
    level: AlertLevel
    reason_codes: list[str]
    created_at: datetime = Field(default_factory=utc_now)
    raw_dialogue_available: Literal[False] = False


class WallMessage(BaseModel):
    """A counselor-authored message shown to students as an anonymous warm card."""

    message_id: UUID = Field(default_factory=uuid4)
    content: str = Field(min_length=1, max_length=1_000)
    published_at: datetime = Field(default_factory=utc_now)
    topic: str | None = Field(default=None, max_length=80)


class HappyShare(BaseModel):
    """A student-authored positive moment, published to every signed-in user.

    This is the deliberately public counterpart of ``MoodCheckIn``: it is stored with
    ``AccessScope.PUBLIC`` and no expiry, while the check-in stays ``OWNER``-scoped and
    expires in seven days. Nothing here is ever routed to staff alerting.
    """

    share_id: UUID = Field(default_factory=uuid4)
    author_id: str
    author_name: str = Field(default="同学", max_length=40)
    content: str = Field(min_length=1, max_length=500)
    # Client-compressed JPEG/PNG data URL. Optional: text-only shares are common.
    image_data_url: str | None = Field(default=None, max_length=1_400_000)
    cheer_count: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=utc_now)
    visibility: Literal["public"] = "public"


class HappyShareDraft(BaseModel):
    """Validated submission envelope; positivity screening happens in the service layer."""

    content: str = Field(min_length=1, max_length=500)
    image_data_url: str | None = Field(default=None, max_length=1_400_000)
    anonymous: bool = False


class TalkLedgerInput(BaseModel):
    """Counselor-confirmed talking points used to create an archive-ready ledger entry."""

    student_id: str
    counselor_name: str
    meeting_at: datetime
    location: str
    topics: list[str] = Field(min_length=1)
    agreed_actions: list[str] = Field(default_factory=list)
    follow_up_at: datetime | None = None


class TalkLedgerEntry(BaseModel):
    """Structured ledger output; it deliberately does not model an unreviewed transcript."""

    student_id: str
    counselor_name: str
    meeting_at: datetime
    location: str
    topic_summary: str
    agreed_actions: list[str]
    follow_up_at: datetime | None
    archive_status: Literal["draft_for_counselor_review"] = "draft_for_counselor_review"
