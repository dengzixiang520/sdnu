import asyncio
from pathlib import Path

from zhihui_qilu.core.enums import MemoryTier
from zhihui_qilu.memory.models import MemoryRecord
from zhihui_qilu.memory.sqlite import SqliteMemorySystem


def test_sqlite_memory_persists_between_instances(tmp_path: Path) -> None:
    async def exercise() -> None:
        path = tmp_path / "memory.sqlite3"
        first = SqliteMemorySystem(path)
        record = MemoryRecord(user_id="u1", tier=MemoryTier.LONG_TERM, category="profile", value={"preferred_name": "小齐"})
        await first.put(record)
        second = SqliteMemorySystem(path)
        recalled = await second.query(user_id="u1", tier=MemoryTier.LONG_TERM)
        assert recalled[0].value["preferred_name"] == "小齐"
    asyncio.run(exercise())
