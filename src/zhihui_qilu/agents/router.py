"""The SuperAgentRouter coordinates safe L1 skill selection and L2 planning."""

from typing import Iterable

from zhihui_qilu.agents.base import BaseAgent
from zhihui_qilu.core.enums import RouteLevel
from zhihui_qilu.core.errors import SkillNotFoundError
from zhihui_qilu.core.models import AgentRequest, AgentResponse
from zhihui_qilu.core.security import SecurityIsolationGateway
from zhihui_qilu.skills.base import BaseSkill


class SuperAgentRouter(BaseAgent):
    """Planning-decision agent that routes direct capabilities and defers complex work."""

    def __init__(self, gateway: SecurityIsolationGateway, skills: Iterable[BaseSkill] = ()) -> None:
        super().__init__("super-agent-router", "规划决策 Agent", {"route", "plan"})
        self._gateway = gateway
        self._skills: dict[str, BaseSkill] = {}
        for skill in skills:
            self.register_skill(skill)

    def register_skill(self, skill: BaseSkill) -> None:
        """Register a unique business Skill for L1 dispatch."""
        if skill.skill_id in self._skills:
            raise ValueError(f"Duplicate skill id: {skill.skill_id}")
        self._skills[skill.skill_id] = skill

    async def execute(self, request: AgentRequest) -> AgentResponse:
        """Securely perform L1 routing or return the L2 planning skeleton result."""
        if request.capability:
            return await self.route_l1(request)
        return await self.plan_l2(request)

    async def route_l1(self, request: AgentRequest) -> AgentResponse:
        """Route an explicit capability directly to its registered Skill."""
        skill = self._skills.get(request.capability or "")
        if skill is None:
            raise SkillNotFoundError(f"No Skill registered for capability: {request.capability}")
        safe_request = self._gateway.inspect_request(request, skill.allowed_roles)
        response = await skill.execute(safe_request)
        return response.model_copy(update={"route_level": RouteLevel.L1, "routed_to": skill.skill_id})

    async def plan_l2(self, request: AgentRequest) -> AgentResponse:
        """Return a safe planning boundary until L2 orchestration is implemented."""
        self._gateway.inspect_request(request)
        return AgentResponse(success=False, message="该请求需要深度任务规划；L2 规划器将在后续模块接入。", data={"available_capabilities": sorted(self._skills)}, route_level=RouteLevel.L2)
