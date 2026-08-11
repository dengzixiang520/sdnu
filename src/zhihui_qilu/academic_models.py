"""Typed contracts for postgraduate interview simulation and knowledge-note organization."""

from datetime import datetime
from enum import IntEnum, StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from zhihui_qilu.core.models import utc_now


class InterviewDuration(IntEnum):
    """Supported simulation durations in minutes."""

    MINUTES_5 = 5
    MINUTES_15 = 15
    MINUTES_30 = 30


class InterviewStrictness(StrEnum):
    """Questioning style selected by the learner."""

    ENCOURAGING = "encouraging"
    BALANCED = "balanced"
    CHALLENGING = "challenging"


class InterviewFocus(StrEnum):
    """Optional focus used to weight the question plan."""

    BALANCED = "balanced"
    ENGLISH = "english"
    PROFESSIONAL = "professional"


class InterviewConfig(BaseModel):
    """User-selected controls for a mock postgraduate interview."""

    major: str = Field(min_length=1, max_length=120)
    duration_minutes: InterviewDuration = InterviewDuration.MINUTES_15
    strictness: InterviewStrictness = InterviewStrictness.BALANCED
    focus: InterviewFocus = InterviewFocus.BALANCED


class PromptMessage(BaseModel):
    """A provider-neutral message in the simulation's prompt chain."""

    role: StrEnum | str
    content: str


class InterviewQuestion(BaseModel):
    """One planned question with a known language and evaluation intent."""

    sequence: int = Field(ge=1)
    question: str
    language: StrEnum | str
    dimension: str


class InterviewSession(BaseModel):
    """An in-progress interview plan; no camera/audio content is stored here."""

    session_id: UUID = Field(default_factory=uuid4)
    config: InterviewConfig
    prompt_chain: list[PromptMessage]
    questions: list[InterviewQuestion]
    created_at: datetime = Field(default_factory=utc_now)


class DimensionScore(BaseModel):
    """A transparent heuristic score, not a clinical or admissions determination."""

    score: int = Field(ge=0, le=100)
    evidence: str
    recommendation: str


class FiveDimensionEvaluation(BaseModel):
    """JSON-ready assessment across the five white-paper evaluation dimensions."""

    expression: DimensionScore
    professional_knowledge: DimensionScore
    english: DimensionScore
    pressure_resilience: DimensionScore
    emotional_stability: DimensionScore
    disclaimer: str = "该评估基于模拟回答文本的训练性启发式指标，不构成录取、心理或医学结论。"


class TranscriptSegment(BaseModel):
    """Timestamped content extracted from an audio recording or document source."""

    start_seconds: int = Field(ge=0)
    end_seconds: int = Field(ge=0)
    text: str = Field(min_length=1)


class TodoItem(BaseModel):
    """Action item linked to its original transcript timestamp."""

    task: str
    timestamp_seconds: int = Field(ge=0)


class StructuredNote(BaseModel):
    """Three-part structured output for classroom or group-meeting materials."""

    three_sentence_summary: list[str] = Field(min_length=3, max_length=3)
    markdown_knowledge_tree: str
    todo_items: list[TodoItem]
