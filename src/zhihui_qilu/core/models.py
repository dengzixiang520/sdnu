"""Typed data transfer objects for agent requests, responses, and audit events."""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from zhihui_qilu.core.enums import RouteLevel, SecurityEventType, UserRole


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""
    return datetime.now(timezone.utc)


class RequestContext(BaseModel):
    """Verified identity and session metadata attached to an agent request."""

    request_id: UUID = Field(default_factory=uuid4)
    user_id: str
    session_id: str
    role: UserRole = UserRole.STUDENT
    source: str = "web"
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentRequest(BaseModel):
    """Normalized request accepted by the routing federation."""

    capability: str | None = None
    text: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    context: RequestContext


class AgentResponse(BaseModel):
    """Uniform result returned by an Agent or a business Skill."""

    success: bool
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    route_level: RouteLevel | None = None
    routed_to: str | None = None


class SecurityEvent(BaseModel):
    """Privacy-safe event record; it intentionally excludes raw user content."""

    event_type: SecurityEventType
    request_id: UUID
    user_id: str
    occurred_at: datetime = Field(default_factory=utc_now)
    details: dict[str, str] = Field(default_factory=dict)
