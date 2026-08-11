"""SQLite implementation of the three-tier memory port for single-node deployments."""

import asyncio
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import UUID

from zhihui_qilu.core.enums import AccessScope, MemoryTier
from zhihui_qilu.core.models import utc_now
from zhihui_qilu.memory.base import MemorySystem
from zhihui_qilu.memory.models import MemoryRecord


class SqliteMemorySystem(MemorySystem):
    """Durable local memory store; replace with a managed SQL/vector adapter for multi-node scale."""

    def __init__(self, database_path: str | Path) -> None:
        self._path = Path(database_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._initialize()

    def _initialize(self) -> None:
        with sqlite3.connect(self._path) as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS memory_records (
                record_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, tier TEXT NOT NULL,
                session_id TEXT, category TEXT NOT NULL, access_scope TEXT NOT NULL,
                expires_at TEXT, payload TEXT NOT NULL
            )""")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_memory_user ON memory_records(user_id, tier, category)")

    async def put(self, record: MemoryRecord) -> MemoryRecord:
        """Upsert a complete validated record atomically."""
        async with self._lock:
            with sqlite3.connect(self._path) as connection:
                connection.execute("""INSERT OR REPLACE INTO memory_records
                    (record_id, user_id, tier, session_id, category, access_scope, expires_at, payload)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (str(record.record_id), record.user_id, record.tier.value, record.session_id, record.category, record.access_scope.value, record.expires_at.isoformat() if record.expires_at else None, json.dumps(record.model_dump(mode="json"), ensure_ascii=False)))
        return record

    async def query(self, *, user_id: str, tier: MemoryTier | None = None, session_id: str | None = None, category: str | None = None, permitted_scopes: set[AccessScope] | None = None) -> list[MemoryRecord]:
        """Retrieve non-expired records by user and optional filters, enforcing explicit scopes."""
        await self.prune_expired()
        clauses = ["user_id = ?"]
        values: list[str] = [user_id]
        if tier is not None:
            clauses.append("tier = ?"); values.append(tier.value)
        if session_id is not None:
            clauses.append("session_id = ?"); values.append(session_id)
        if category is not None:
            clauses.append("category = ?"); values.append(category)
        scopes = permitted_scopes or {AccessScope.OWNER}
        placeholders = ", ".join("?" for _ in scopes)
        clauses.append(f"access_scope IN ({placeholders})")
        values.extend(scope.value for scope in scopes)
        async with self._lock:
            with sqlite3.connect(self._path) as connection:
                rows = connection.execute(f"SELECT payload FROM memory_records WHERE {' AND '.join(clauses)} ORDER BY rowid", values).fetchall()
        return [MemoryRecord.model_validate_json(row[0]) for row in rows]

    async def forget(self, record_id: UUID) -> bool:
        """Delete one record as part of a user's right-to-erasure workflow."""
        async with self._lock:
            with sqlite3.connect(self._path) as connection:
                cursor = connection.execute("DELETE FROM memory_records WHERE record_id = ?", (str(record_id),))
                return cursor.rowcount > 0

    async def forget_user(self, user_id: str) -> int:
        """Delete all memory tiers for one user in a single transaction."""
        async with self._lock:
            with sqlite3.connect(self._path) as connection:
                cursor = connection.execute("DELETE FROM memory_records WHERE user_id = ?", (user_id,))
                return cursor.rowcount

    async def prune_expired(self, now: datetime | None = None) -> int:
        """Purge expired ephemeral and short-term records."""
        cutoff = (now or utc_now()).isoformat()
        async with self._lock:
            with sqlite3.connect(self._path) as connection:
                cursor = connection.execute("DELETE FROM memory_records WHERE expires_at IS NOT NULL AND expires_at <= ?", (cutoff,))
                return cursor.rowcount

    async def compress_long_term(self, user_id: str) -> int:
        """Expose the same reviewed future-compression hook as the in-memory backend."""
        return len(await self.query(user_id=user_id, tier=MemoryTier.LONG_TERM))
