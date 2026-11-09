"""Storage-port definition for pluggable memory backends."""

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from zhihui_qilu.core.enums import AccessScope, MemoryTier
from zhihui_qilu.memory.models import MemoryRecord


class MemorySystem(ABC):
    """Port implemented by in-memory, Redis, SQL, or vector-backed memory systems."""

    @abstractmethod
    async def put(self, record: MemoryRecord) -> MemoryRecord: ...

    @abstractmethod
    async def query(self, *, user_id: str | None = None, tier: MemoryTier | None = None, session_id: str | None = None, category: str | None = None, permitted_scopes: set[AccessScope] | None = None) -> list[MemoryRecord]:
        """Retrieve records; ``user_id=None`` means "any owner" and is reserved for
        authorized staff retrieval, which must always pass explicit scopes."""
        ...

    @abstractmethod
    async def forget(self, record_id: UUID) -> bool: ...

    @abstractmethod
    async def forget_user(self, user_id: str) -> int: ...

    @abstractmethod
    async def prune_expired(self, now: datetime | None = None) -> int: ...

    @abstractmethod
    async def compress_long_term(self, user_id: str) -> int:
        """Future hook for summarizing related durable memories without raw-data loss."""
