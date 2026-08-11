import asyncio
from collections.abc import AsyncIterator

from zhihui_qilu.ai.provider import ChatMessage, LanguageModelProvider, OfflineProvider
from zhihui_qilu.ai.service import CampusConversationService
from zhihui_qilu.config import Settings
from zhihui_qilu.memory.in_memory import InMemoryMemorySystem


class FakeProvider(LanguageModelProvider):
    @property
    def available(self) -> bool:
        return True

    async def complete(self, messages: list[ChatMessage], *, temperature: float = 0.6) -> str:
        assert messages[-1].content == "今天有点焦虑"
        return "我听见了。愿意说说最让你紧张的是哪件事吗？"

    async def stream(self, messages: list[ChatMessage], *, temperature: float = 0.6) -> AsyncIterator[str]:
        del messages, temperature
        for chunk in ("请介绍", "你的项目。"):
            yield chunk


def test_chat_remembers_turns_and_blocks_crisis_from_provider() -> None:
    async def exercise() -> None:
        memory = InMemoryMemorySystem()
        service = CampusConversationService(FakeProvider(), memory, Settings(environment="test"))
        result = await service.reply(mode="wellbeing", user_id="u1", session_id="s1", message="今天有点焦虑")
        assert result.provider_online and "紧张" in result.reply
        assert len(await service.history(mode="wellbeing", user_id="u1", session_id="s1")) == 2
        crisis = await service.reply(mode="wellbeing", user_id="u1", session_id="s1", message="我不想活了")
        assert crisis.escalated and crisis.state == "caring"

    asyncio.run(exercise())


def test_interview_stream_is_accumulated_and_remembered() -> None:
    async def exercise() -> None:
        service = CampusConversationService(FakeProvider(), InMemoryMemorySystem(), Settings(environment="test"))
        events = [event async for event in service.stream(mode="academic_interview", user_id="u2", session_id="s2", message="开始", metadata={"major": "人工智能"})]
        assert "".join(str(value) for event_type, value in events if event_type == "token") == "请介绍你的项目。"
        assert len(await service.history(mode="academic_interview", user_id="u2", session_id="s2")) == 2

    asyncio.run(exercise())


def test_offline_provider_recognizes_postgraduate_interview_prompt() -> None:
    """The fallback must not answer interview sessions as a wellbeing guide."""

    async def exercise() -> None:
        provider = OfflineProvider()
        result = await provider.complete(
            [
                ChatMessage(role="system", content="你是研究生复试训练导师，每次只提出一个具体问题。"),
                ChatMessage(role="user", content="请开始一场模拟复试。"),
            ]
        )
        assert "项目" in result
        assert "我在这里" not in result

    asyncio.run(exercise())
