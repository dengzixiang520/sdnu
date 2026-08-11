"""Base contract for all autonomous platform agents."""

from abc import ABC, abstractmethod

from zhihui_qilu.core.models import AgentRequest, AgentResponse


class BaseAgent(ABC):
    """Every agent has a stable identity, declared capabilities, and async execution."""

    agent_id: str
    display_name: str
    capabilities: frozenset[str]

    def __init__(self, agent_id: str, display_name: str, capabilities: set[str] | frozenset[str]) -> None:
        self.agent_id = agent_id
        self.display_name = display_name
        self.capabilities = frozenset(capabilities)

    async def startup(self) -> None:
        """Initialize optional resources; subclasses may override."""

    async def shutdown(self) -> None:
        """Release optional resources; subclasses may override."""

    @abstractmethod
    async def execute(self, request: AgentRequest) -> AgentResponse:
        """Execute an approved request and return a structured result."""
