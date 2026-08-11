"""Non-sensitive health endpoint for platform probes."""

from fastapi import APIRouter, Request

router = APIRouter(tags=["system"])


@router.get("/healthz")
async def health_check(request: Request) -> dict[str, str]:
    """Report liveness without disclosing configuration or secrets."""
    return {"status": "ok", "service": request.app.state.container.settings.app_name}
