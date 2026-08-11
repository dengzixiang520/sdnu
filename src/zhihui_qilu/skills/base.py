"""Common interface used by the L1 router to invoke a business capability."""

from abc import ABC, abstractmethod

from zhihui_qilu.core.enums import UserRole
from zhihui_qilu.core.models import AgentRequest, AgentResponse


class BaseSkill(ABC):
    """An independently deployable, permission-scoped business capability."""

    skill_id: str
    display_name: str
    allowed_roles: set[UserRole] = {UserRole.STUDENT, UserRole.COUNSELOR, UserRole.ADMINISTRATOR}

    @abstractmethod
    async def execute(self, request: AgentRequest) -> AgentResponse: ...
