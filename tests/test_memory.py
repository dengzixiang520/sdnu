import asyncio
from datetime import timedelta

from zhihui_qilu.core.enums import AccessScope, MemoryTier
from zhihui_qilu.core.models import utc_now
from zhihui_qilu.memory.in_memory import InMemoryMemorySystem
from zhihui_qilu.memory.models import MemoryRecord


def test_memory_filters_scope_and_prunes_expiry() -> None:
    asyncio.run(_exercise_memory())


async def _exercise_memory() -> None:
    memory = InMemoryMemorySystem()
    owner = MemoryRecord(user_id="u1", tier=MemoryTier.LONG_TERM, category="skills", value={"items": ["Python"]})
    staff = MemoryRecord(user_id="u1", tier=MemoryTier.SHORT_TERM, category="schedule", value={}, access_scope=AccessScope.AUTHORIZED_STAFF)
    expired = MemoryRecord(user_id="u1", tier=MemoryTier.EPHEMERAL, category="draft", value={}, expires_at=utc_now() - timedelta(seconds=1))
    for record in (owner, staff, expired):
        await memory.put(record)
    assert [r.record_id for r in await memory.query(user_id="u1")] == [owner.record_id]
    visible_to_staff = await memory.query(user_id="u1", permitted_scopes={AccessScope.AUTHORIZED_STAFF})
    assert [r.record_id for r in visible_to_staff] == [staff.record_id]
    assert await memory.forget_user("u1") == 2
