"""Named interfaces for the five white-paper Agent roles."""

from abc import abstractmethod
from typing import Any

from zhihui_qilu.agents.base import BaseAgent
from zhihui_qilu.core.models import AgentRequest, AgentResponse
from zhihui_qilu.memory.models import MemoryRecord


class PerceptionAgent(BaseAgent):
    """Transforms text, files, voice, vision, and timetable inputs into structured data."""

    @abstractmethod
    async def perceive(self, raw_input: Any, request: AgentRequest) -> dict[str, Any]: ...


class MemoryAgent(BaseAgent):
    """Provides controlled storage, recall, compression, and forgetting services."""

    @abstractmethod
    async def remember(self, record: MemoryRecord) -> MemoryRecord: ...


class PlanningDecisionAgent(BaseAgent):
    """Performs L1 skill routing and L2 multi-step planning."""

    @abstractmethod
    async def plan(self, request: AgentRequest) -> AgentResponse: ...


class SecurityPrivacyAgent(BaseAgent):
    """Independently enforces data privacy and security policies."""

    @abstractmethod
    async def validate(self, request: AgentRequest) -> AgentRequest: ...


class ExecutionAgent(BaseAgent):
    """Dispatches authorized skills to web, mobile, and service endpoints."""

    @abstractmethod
    async def dispatch(self, request: AgentRequest) -> AgentResponse: ...
