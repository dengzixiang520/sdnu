"""Language-model provider ports and the DeepSeek HTTP adapter."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Literal

import httpx
from pydantic import BaseModel


class ChatMessage(BaseModel):
    """Provider-neutral chat message used by all campus conversation modes."""

    role: Literal["system", "user", "assistant"]
    content: str


class ProviderUnavailableError(RuntimeError):
    """Raised when a configured AI provider cannot return a safe completion."""


class LanguageModelProvider(ABC):
    """Minimal asynchronous interface implemented by approved LLM providers."""

    @property
    @abstractmethod
    def available(self) -> bool:
        """Return whether this provider is configured for real inference."""

    @abstractmethod
    async def complete(self, messages: list[ChatMessage], *, temperature: float = 0.6) -> str:
        """Return one complete assistant message."""

    @abstractmethod
    async def stream(self, messages: list[ChatMessage], *, temperature: float = 0.6) -> AsyncIterator[str]:
        """Yield assistant text deltas in provider order."""


class DeepSeekProvider(LanguageModelProvider):
    """DeepSeek's OpenAI-compatible chat-completions adapter."""

    def __init__(self, *, api_key: str, base_url: str, model: str, connect_timeout: float, read_timeout: float) -> None:
        self._api_key = api_key
        self._endpoint = f"{base_url.rstrip('/')}/chat/completions"
        self._model = model
        self._timeout = httpx.Timeout(connect=connect_timeout, read=read_timeout, write=20.0, pool=10.0)

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    def _payload(self, messages: list[ChatMessage], *, temperature: float, stream: bool) -> dict[str, object]:
        return {
            "model": self._model,
            "messages": [message.model_dump() for message in messages],
            "temperature": temperature,
            "stream": stream,
        }

    async def complete(self, messages: list[ChatMessage], *, temperature: float = 0.6) -> str:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    self._endpoint,
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json=self._payload(messages, temperature=temperature, stream=False),
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                if not isinstance(content, str) or not content.strip():
                    raise ProviderUnavailableError("DeepSeek returned an empty completion")
                return content.strip()
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise ProviderUnavailableError("DeepSeek request failed") from exc

    async def stream(self, messages: list[ChatMessage], *, temperature: float = 0.6) -> AsyncIterator[str]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST",
                    self._endpoint,
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json=self._payload(messages, temperature=temperature, stream=True),
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        payload = line[6:].strip()
                        if payload == "[DONE]":
                            return
                        try:
                            data = __import__("json").loads(payload)
                            delta = data["choices"][0]["delta"].get("content")
                        except (KeyError, TypeError, ValueError):
                            continue
                        if isinstance(delta, str) and delta:
                            yield delta
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError("DeepSeek streaming request failed") from exc


class OfflineProvider(LanguageModelProvider):
    """Deterministic local fallback that keeps development flows usable without a key."""

    @property
    def available(self) -> bool:
        return False

    async def complete(self, messages: list[ChatMessage], *, temperature: float = 0.6) -> str:
        del temperature
        latest = next((item.content for item in reversed(messages) if item.role == "user"), "")
        system_prompt = messages[0].content if messages else ""
        if any(term in system_prompt for term in ("面试", "复试", "训练导师")):
            return "请结合一个你真正参与过的项目，说明你负责的核心问题、验证方法，以及结果不符合预期时你如何调整。"
        if any(word in latest for word in ("焦虑", "压力", "难受", "睡不着")):
            return "听起来你正在承受不少压力。我们可以先把最困扰你的那一件事说清楚，也可以先做一分钟呼吸练习。此刻最难熬的是哪一部分？"
        return "我在这里。你可以从今天发生的一件小事说起，也可以只告诉我此刻更想被倾听，还是一起想办法。"

    async def stream(self, messages: list[ChatMessage], *, temperature: float = 0.6) -> AsyncIterator[str]:
        reply = await self.complete(messages, temperature=temperature)
        for character in reply:
            yield character
