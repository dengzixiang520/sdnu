"""Concurrency-safe reference backend for local development and tests."""

import asyncio
from datetime import datetime
from uuid import UUID

from zhihui_qilu.core.enums import AccessScope, MemoryTier
from zhihui_qilu.core.models import utc_now
from zhihui_qilu.memory.base import MemorySystem
from zhihui_qilu.memory.models import MemoryRecord


class InMemoryMemorySystem(MemorySystem):
    """Process-local memory repository; replace with a durable adapter for deployment."""

    def __init__(self) -> None:
        self._records: dict[UUID, MemoryRecord] = {}
        self._lock = asyncio.Lock()

    async def put(self, record: MemoryRecord) -> MemoryRecord:
        async with self._lock:
            self._records[record.record_id] = record
        return record

    async def query(self, *, user_id: str | None = None, tier: MemoryTier | None = None, session_id: str | None = None, category: str | None = None, permitted_scopes: set[AccessScope] | None = None) -> list[MemoryRecord]:
        await self.prune_expired()
        scopes = permitted_scopes or {AccessScope.OWNER}
        async with self._lock:
            return [record for record in self._records.values() if (user_id is None or record.user_id == user_id) and (tier is None or record.tier == tier) and (session_id is None or record.session_id == session_id) and (category is None or record.category == category) and record.access_scope in scopes]

    async def forget(self, record_id: UUID) -> bool:
        async with self._lock:
            return self._records.pop(record_id, None) is not None

    async def forget_user(self, user_id: str) -> int:
        async with self._lock:
            record_ids = [record_id for record_id, record in self._records.items() if record.user_id == user_id]
            for record_id in record_ids:
                del self._records[record_id]
            return len(record_ids)

    async def prune_expired(self, now: datetime | None = None) -> int:
        current = now or utc_now()
        async with self._lock:
            expired_ids = [record_id for record_id, record in self._records.items() if record.is_expired(current)]
            for record_id in expired_ids:
                del self._records[record_id]
            return len(expired_ids)

    async def compress_long_term(self, user_id: str) -> int:
        """Deliberately a no-op until a reviewed, domain-specific compression policy exists."""
        return len(await self.query(user_id=user_id, tier=MemoryTier.LONG_TERM))
