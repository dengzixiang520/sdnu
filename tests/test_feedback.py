"""学生评价的回归测试。

「用户评分」是赛题写明的评审维度之一，所以这里要证明三件事：
评价真的存下来了、聚合数字算得对、写错对象名不会被静默吞掉。

项目约定用 ``asyncio.run`` 而不是 pytest-asyncio，这里保持一致。
"""

import asyncio

import pytest

from zhihui_qilu.feedback_service import NOTE_MAX_CHARS, TARGETS, FeedbackService
from zhihui_qilu.memory.in_memory import InMemoryMemorySystem


@pytest.fixture()
def service() -> FeedbackService:
    return FeedbackService(InMemoryMemorySystem())


def test_record_then_summary_counts_one(service: FeedbackService) -> None:
    """一条好评进去，有用率就是 100%。"""

    async def exercise() -> dict:
        await service.record(
            user_id="student-1",
            session_id="session-1",
            target="doc_normalize",
            helpful=True,
        )
        return await service.summary()

    summary = asyncio.run(exercise())
    assert summary["total"] == 1
    assert summary["helpful"] == 1
    assert summary["rate"] == 100
    assert summary["by_target"][0]["target"] == "doc_normalize"
    assert summary["by_target"][0]["target_name"] == "公文规范化"


def test_rate_is_computed_across_users(service: FeedbackService) -> None:
    """跨用户聚合：2 好 1 差 = 67%。"""

    async def exercise() -> dict:
        await service.record(user_id="a", session_id="s", target="wellbeing_chat", helpful=True)
        await service.record(user_id="b", session_id="s", target="wellbeing_chat", helpful=True)
        await service.record(user_id="c", session_id="s", target="wellbeing_chat", helpful=False)
        return await service.summary()

    summary = asyncio.run(exercise())
    assert summary["total"] == 3
    assert summary["rate"] == 67
    assert summary["by_target"][0]["total"] == 3


def test_unknown_target_is_rejected(service: FeedbackService) -> None:
    """对象名写错要报错，不能写进去当垃圾数据。"""
    with pytest.raises(ValueError) as error:
        asyncio.run(
            service.record(user_id="a", session_id="s", target="not-a-target", helpful=True)
        )
    assert "不认识" in str(error.value)


def test_note_is_trimmed_and_capped(service: FeedbackService) -> None:
    """一句话评价去掉多余空白并截断，防止贴一整篇。"""

    async def exercise() -> dict:
        await service.record(
            user_id="a",
            session_id="s",
            target="interview_report",
            helpful=False,
            note="  说了很多\n\n但没讲清楚   " + "长" * 400,
        )
        return await service.summary()

    summary = asyncio.run(exercise())
    assert summary["recent_notes"]
    note = summary["recent_notes"][0]
    assert "\n" not in note
    assert len(note) <= NOTE_MAX_CHARS


def test_empty_summary_says_so(service: FeedbackService) -> None:
    """没人评价时不能假装有数据。"""
    summary = asyncio.run(service.summary())
    assert summary["total"] == 0
    assert summary["rate"] == 0
    assert summary["by_target"] == []
    assert "还没有人评价" in summary["note"]


def test_targets_cover_the_five_scored_modules() -> None:
    """五个能拿分的模块都要能评价，漏一个就等于那个模块没有用户评分。"""
    for key in ("wellbeing_chat", "interview_report", "doc_normalize", "credit_warning", "proposal_outline"):
        assert key in TARGETS
