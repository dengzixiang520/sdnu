"""Temporary development identity boundary until school SSO/JWT integration is available."""

from fastapi import Header, HTTPException, Request, status

from zhihui_qilu.core.enums import UserRole
from zhihui_qilu.core.models import RequestContext


async def get_development_context(
    request: Request,
    x_user_id: str | None = Header(default=None),
    x_session_id: str | None = Header(default=None),
    x_user_role: UserRole = Header(default=UserRole.STUDENT),
) -> RequestContext:
    """Create a request context only in non-production environments.

    This is deliberately a development adapter, not an authentication mechanism.
    Production deployment must replace it with verified SSO/JWT claims.
    """
    if request.app.state.container.settings.environment == "production":
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Production SSO/JWT authentication adapter has not been configured")
    if not x_user_id or not x_session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="X-User-Id and X-Session-Id headers are required in development")
    return RequestContext(user_id=x_user_id, session_id=x_session_id, role=x_user_role)
