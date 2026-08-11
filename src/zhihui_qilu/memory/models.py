"""Memory records shared across the three retention tiers."""

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from zhihui_qilu.core.enums import AccessScope, MemoryTier, SensitivityLevel
from zhihui_qilu.core.models import utc_now


class MemoryRecord(BaseModel):
    """A tagged, access-controlled unit of memory with optional expiry."""

    record_id: UUID = Field(default_factory=uuid4)
    user_id: str
    tier: MemoryTier
    category: str
    value: dict[str, Any]
    session_id: str | None = None
    source_agent: str = "unknown"
    access_scope: AccessScope = AccessScope.OWNER
    sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None
    tags: set[str] = Field(default_factory=set)
    audit_metadata: dict[str, str] = Field(default_factory=dict)

    def is_expired(self, at: datetime | None = None) -> bool:
        """Return whether the record's retention deadline has passed."""
        return self.expires_at is not None and self.expires_at <= (at or utc_now())

    @classmethod
    def ephemeral(cls, *, user_id: str, session_id: str, category: str, value: dict[str, Any], ttl_seconds: int, **kwargs: Any) -> "MemoryRecord":
        """Create a four-hour-style session record with explicit expiry."""
        return cls(user_id=user_id, session_id=session_id, tier=MemoryTier.EPHEMERAL, category=category, value=value, expires_at=utc_now() + timedelta(seconds=ttl_seconds), **kwargs)
