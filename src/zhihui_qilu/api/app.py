"""FastAPI factory to keep startup configuration testable."""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from zhihui_qilu.api.routes.agent import router as agent_router
from zhihui_qilu.api.routes.chat import router as chat_router
from zhihui_qilu.api.routes.competition import router as competition_router
from zhihui_qilu.api.routes.timetable import router as timetable_router
from zhihui_qilu.api.routes.points import router as points_router
from zhihui_qilu.api.routes.exchange import router as exchange_router
from zhihui_qilu.api.routes.documents import router as documents_router
from zhihui_qilu.api.routes.evidence import router as evidence_router
from zhihui_qilu.api.routes.feedback import router as feedback_router
from zhihui_qilu.api.routes.integration import router as integration_router
from zhihui_qilu.api.routes.interview import router as interview_router
from zhihui_qilu.api.routes.study_plan import router as study_plan_router
from zhihui_qilu.api.routes.health import router as health_router
from zhihui_qilu.api.routes.music import router as music_router
from zhihui_qilu.api.routes.poster import router as poster_router
from zhihui_qilu.bootstrap import PlatformContainer
from zhihui_qilu.config import Settings


def create_app(settings: Settings) -> FastAPI:
    """Create the Task 1 HTTP application and attach the platform container."""
    container = PlatformContainer(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.container = container
        await container.seed_demo_content()
        try:
            yield
        finally:
            close = getattr(container.ai_provider, "close", None)
            if close is not None:
                await close()
            await container.speech.close()
            await container.asr.close()

    app = FastAPI(title=settings.app_name, version="0.1.0", debug=settings.debug, lifespan=lifespan)
    # Keep container available even before lifespan startup (tests and direct ASGI inspection).
    app.state.container = container
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-User-Id", "X-Session-Id", "X-User-Role"],
    )
    app.include_router(health_router)
    app.include_router(agent_router)
    app.include_router(chat_router)
    app.include_router(competition_router)
    app.include_router(timetable_router)
    app.include_router(points_router)
    app.include_router(exchange_router)
    app.include_router(documents_router)
    app.include_router(evidence_router)
    app.include_router(feedback_router)
    app.include_router(interview_router)
    app.include_router(study_plan_router)
    app.include_router(integration_router)
    app.include_router(music_router)
    app.include_router(poster_router)
    return app
