import logging

from fastapi import APIRouter, Depends, HTTPException, Response

from app.core.auth import (
    SESSION_COOKIE_NAME,
    authentication_configured,
    create_session_token,
    require_staff_session,
    verify_admin_password,
)
from app.core.config import settings
from app.schema.schema_ import AdminLoginRequest, AuthStatusResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)


@router.post("/login", response_model=AuthStatusResponse)
async def login(data: AdminLoginRequest, response: Response) -> AuthStatusResponse:
    if not authentication_configured():
        logger.error("staff_authentication_not_configured")
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    if not verify_admin_password(data.password):
        logger.warning("staff_login_failed")
        raise HTTPException(status_code=401, detail="invalid_credentials")

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=create_session_token(),
        max_age=settings.SESSION_TTL_SECONDS,
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        samesite="strict",
        path="/api",
    )
    logger.info("staff_login_succeeded")
    return AuthStatusResponse(authenticated=True)


@router.post("/logout", response_model=AuthStatusResponse)
async def logout(response: Response) -> AuthStatusResponse:
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/api")
    logger.info("staff_logout_completed")
    return AuthStatusResponse(authenticated=False)


@router.get("/me", response_model=AuthStatusResponse)
async def me(_: None = Depends(require_staff_session)) -> AuthStatusResponse:
    return AuthStatusResponse(authenticated=True)
