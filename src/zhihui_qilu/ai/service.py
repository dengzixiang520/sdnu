"""Safe multi-turn conversation service shared by the guide and interview room."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timezone
from typing import Literal

from zhihui_qilu.ai.persona import compose_guide_prompt
from zhihui_qilu.ai.provider import ChatMessage, LanguageModelProvider, ProviderUnavailableError
from zhihui_qilu.config import Settings
from zhihui_qilu.core.enums import AccessScope, MemoryTier, SensitivityLevel
from zhihui_qilu.core.models import utc_now
from zhihui_qilu.memory.base import MemorySystem
from zhihui_qilu.memory.models import MemoryRecord

ConversationMode = Literal["wellbeing", "academic_interview"]


@dataclass(slots=True)
class ConversationResult:
    """One safe assistant turn and the UI state it should communicate."""

    reply: str
    state: Literal["talking", "caring", "thinking"] = "talking"
    escalated: bool = False
    provider_online: bool = True


class CampusConversationService:
    """Build prompts, recall bounded session context, and persist redacted turns."""

    _CRISIS_TERMS = ("自杀", "自残", "结束生命", "不想活", "轻生", "suicide", "kill myself")
    _CRISIS_REPLY = (
        "我很在意你现在的安全。请先不要独自承受，立即联系身边可信任的人、辅导员或当地紧急服务；"
        "也可以直接拨打 24 小时心理援助热线 12356，或通过 QQ 2645256823 联系山师心灵阳光使者。"
        "如果存在马上伤害自己的可能，请离开危险物品并前往有人陪伴的地方。你可以只回复我：现在是否安全、身边是否有人。"
    )

    def __init__(self, provider: LanguageModelProvider, memory: MemorySystem, settings: Settings) -> None:
        self._provider = provider
        self._memory = memory
        self._settings = settings

    async def reply(self, *, mode: ConversationMode, user_id: str, session_id: str, message: str, metadata: dict[str, str] | None = None) -> ConversationResult:
        """Return one assistant turn, bypassing the LLM for deterministic crisis handling."""
        if self._is_crisis(message):
            await self._remember(mode, user_id, session_id, "user", message)
            await self._remember(mode, user_id, session_id, "assistant", self._CRISIS_REPLY)
            return ConversationResult(reply=self._CRISIS_REPLY, state="caring", escalated=True, provider_online=self._provider.available)
        messages = await self._build_messages(mode, user_id, session_id, message, metadata)
        try:
            reply = await self._provider.complete(messages, temperature=0.55 if mode == "wellbeing" else 0.7)
            online = self._provider.available
        except ProviderUnavailableError:
            from zhihui_qilu.ai.provider import OfflineProvider

            reply = await OfflineProvider().complete(messages)
            online = False
        await self._remember(mode, user_id, session_id, "user", message)
        await self._remember(mode, user_id, session_id, "assistant", reply)
        return ConversationResult(reply=reply, provider_online=online)

    async def stream(self, *, mode: ConversationMode, user_id: str, session_id: str, message: str, metadata: dict[str, str] | None = None) -> AsyncIterator[tuple[str, str | bool]]:
        """Yield typed stream events and remember the completed response exactly once."""
        if self._is_crisis(message):
            await self._remember(mode, user_id, session_id, "user", message)
            for character in self._CRISIS_REPLY:
                yield "token", character
            await self._remember(mode, user_id, session_id, "assistant", self._CRISIS_REPLY)
            yield "escalated", True
            return
        messages = await self._build_messages(mode, user_id, session_id, message, metadata)
        chunks: list[str] = []
        online = self._provider.available
        try:
            async for chunk in self._provider.stream(messages, temperature=0.55 if mode == "wellbeing" else 0.7):
                chunks.append(chunk)
                yield "token", chunk
        except ProviderUnavailableError:
            from zhihui_qilu.ai.provider import OfflineProvider

            online = False
            async for chunk in OfflineProvider().stream(messages):
                chunks.append(chunk)
                yield "token", chunk
        reply = "".join(chunks).strip()
        await self._remember(mode, user_id, session_id, "user", message)
        await self._remember(mode, user_id, session_id, "assistant", reply)
        yield "provider_online", online

    async def history(self, *, mode: ConversationMode, user_id: str, session_id: str) -> list[ChatMessage]:
        """Return the recent owner-only conversation history for the current session."""
        records = await self._memory.query(user_id=user_id, session_id=session_id, category=f"conversation.{mode}")
        records.sort(key=lambda item: item.created_at)
        result: list[ChatMessage] = []
        for record in records[-self._settings.ai_max_context_messages :]:
            role = record.value.get("role")
            content = record.value.get("content")
            if role in {"user", "assistant"} and isinstance(content, str):
                result.append(ChatMessage(role=role, content=content))
        return result

    async def _build_messages(self, mode: ConversationMode, user_id: str, session_id: str, message: str, metadata: dict[str, str] | None) -> list[ChatMessage]:
        # 心情上下文一律后端算，不采信前端传来的状态
        context = await self._guide_context(user_id) if mode == "wellbeing" else {}
        system = self._system_prompt(mode, {**(metadata or {}), **context})
        history = await self.history(mode=mode, user_id=user_id, session_id=session_id)
        return [ChatMessage(role="system", content=system), *history, ChatMessage(role="user", content=message)]

    async def _guide_context(self, user_id: str) -> dict[str, str]:
        """从短期记忆里取最近心情，喂给 system prompt 做语气校准。"""
        try:
            records = await self._memory.query(user_id=user_id, tier=MemoryTier.SHORT_TERM, category="wellbeing.mood_checkin")
        except Exception:  # noqa: BLE001 - 记忆读失败不该拖垮对话
            return {}
        checkins: list[tuple[object, str]] = []
        for record in records:
            weather = record.value.get("weather")
            checked_at = record.value.get("checked_at")
            if isinstance(checked_at, str):
                checkins.append((checked_at, str(weather or "")))
        if not checkins:
            return {}
        checkins.sort(key=lambda item: str(item[0]))
        latest_at, latest_weather = checkins[-1]
        negative = sum(1 for _, weather in checkins if weather in {"rainy", "stormy"})
        level = "green"
        if negative >= 5:
            level = "orange"
        elif negative >= 3:
            level = "yellow"
        today = utc_now().astimezone(timezone.utc).date().isoformat()
        return {
            "mood": latest_weather,
            "alert_level": level,
            "checked_today": "1" if str(latest_at)[:10] == today else "0",
        }

    def _system_prompt(self, mode: ConversationMode, metadata: dict[str, str]) -> str:
        if mode == "academic_interview":
            major = metadata.get("major", "用户选择的专业")
            focus = metadata.get("focus", "均衡")
            return (
                f"你是研究生复试训练导师，目标专业是{major}，侧重{focus}。每次只提出一个具体问题，"
                "根据上一轮回答进行自然追问。保持专业、清晰和有压力但不羞辱；不要承诺录取，不编造院校政策。"
            )
        return compose_guide_prompt(metadata)

    async def _remember(self, mode: ConversationMode, user_id: str, session_id: str, role: str, content: str) -> None:
        await self._memory.put(
            MemoryRecord.ephemeral(
                user_id=user_id,
                session_id=session_id,
                category=f"conversation.{mode}",
                value={"role": role, "content": content},
                ttl_seconds=self._settings.ephemeral_memory_ttl_seconds,
                source_agent="campus-conversation-service",
                access_scope=AccessScope.OWNER,
                sensitivity=SensitivityLevel.SENSITIVE,
            )
        )

    @classmethod
    def _is_crisis(cls, message: str) -> bool:
        lowered = message.lower()
        return any(term in lowered for term in cls._CRISIS_TERMS)
