"""演示播种的回归测试。

线下展示时评委可能自己点开寄语墙和分享墙，两片空白会显得平台没人用。
播种只补空、不覆盖，生产环境不执行——这三条都要钉住。
"""

import asyncio

from zhihui_qilu.bootstrap import PlatformContainer
from zhihui_qilu.config import Settings
from zhihui_qilu.wellbeing_models import WallMessage


def build(environment: str = "test") -> PlatformContainer:
    return PlatformContainer(Settings(memory_backend="memory", environment=environment))


def test_seed_fills_empty_lists() -> None:
    """空库启动后寄语、分享、评价都有内容，不再是一片空白。"""
    container = build()
    asyncio.run(container.seed_demo_content())

    assert len(asyncio.run(container.wellbeing.list_wall_messages())) == 2
    assert len(asyncio.run(container.wellbeing.list_happy_shares())) == 2
    summary = asyncio.run(container.feedback.summary())
    assert summary["total"] == 8
    assert summary["rate"] == 75


def test_seed_feedback_has_both_verdicts() -> None:
    """评价种子必须有好有差，全是好评反而不可信。"""
    container = build()
    asyncio.run(container.seed_demo_content())

    summary = asyncio.run(container.feedback.summary())
    assert 0 < summary["helpful"] < summary["total"]
    assert summary["recent_notes"], "差评要带一句具体的话，不能只有分数"


def test_seed_never_overwrites_existing_content() -> None:
    """已经有内容时不能再塞，否则每重启一次就多两条。"""

    async def exercise() -> int:
        await container.wellbeing.publish_wall_message(WallMessage(content="辅导员自己写的", topic="真实"))
        await container.seed_demo_content()
        return len(await container.wellbeing.list_wall_messages())

    container = build()
    assert asyncio.run(exercise()) == 1


def test_seed_is_skipped_in_production() -> None:
    """生产环境不播种，不能把演示内容混进真实数据。"""
    container = build("production")
    asyncio.run(container.seed_demo_content())

    assert asyncio.run(container.wellbeing.list_wall_messages()) == []
    assert asyncio.run(container.wellbeing.list_happy_shares()) == []
    assert asyncio.run(container.feedback.summary())["total"] == 0


def test_seed_twice_is_idempotent() -> None:
    """连跑两次结果一样，重启多少次都不会堆内容。"""
    container = build()
    asyncio.run(container.seed_demo_content())
    asyncio.run(container.seed_demo_content())

    assert len(asyncio.run(container.wellbeing.list_wall_messages())) == 2
    assert len(asyncio.run(container.wellbeing.list_happy_shares())) == 2
    assert asyncio.run(container.feedback.summary())["total"] == 8
