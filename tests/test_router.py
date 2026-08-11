import asyncio

from zhihui_qilu.agents.router import SuperAgentRouter
from zhihui_qilu.config import Settings
from zhihui_qilu.core.models import AgentRequest, AgentResponse, RequestContext
from zhihui_qilu.core.security import SecurityIsolationGateway
from zhihui_qilu.skills.base import BaseSkill


class EchoSkill(BaseSkill):
    skill_id = "echo"
    display_name = "Echo"

    async def execute(self, request: AgentRequest) -> AgentResponse:
        return AgentResponse(success=True, message=request.text)


def test_router_routes_registered_skill_and_defers_l2() -> None:
    asyncio.run(_exercise_router())


async def _exercise_router() -> None:
    router = SuperAgentRouter(SecurityIsolationGateway(Settings()), [EchoSkill()])
    request = AgentRequest(capability="echo", text="hello", context=RequestContext(user_id="u1", session_id="s1"))
    response = await router.execute(request)
    assert response.success and response.routed_to == "echo"
    deferred = await router.execute(request.model_copy(update={"capability": None}))
    assert not deferred.success and deferred.route_level == "l2"
