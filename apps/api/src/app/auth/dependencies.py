from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy import create_engine

from app.settings import get_settings

from .models import AdminAccount
from .repository import AuthRepository
from .schemas import AuthContext
from .service import AuthError, AuthService


def build_auth_service(settings=None) -> AuthService:
    settings = settings or get_settings()
    repository = AuthRepository(
        create_engine(settings.sqlite_url),
        max_failures=settings.auth_login_max_failures,
        lock_seconds=settings.auth_login_lock_seconds,
    )
    return AuthService(repository, settings)


def get_auth_service(request: Request) -> AuthService:
    value = getattr(request.app.state, "auth_service", None)
    return value if value is not None else build_auth_service()


def auth_http_error(error: AuthError) -> HTTPException:
    detail: dict[str, object] = {"code": error.code, **error.details}
    headers = {"Retry-After": str(error.retry_after_seconds)} if error.retry_after_seconds else None
    return HTTPException(status_code=error.status_code, detail=detail, headers=headers)


def require_session(request: Request, service: AuthService = Depends(get_auth_service)) -> AuthContext:
    try:
        token = request.cookies.get(service.settings.auth_cookie_name)
        context = service.authenticate(token)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            service.verify_csrf(context, request.headers.get("X-CSRF-Token", ""))
        return context
    except AuthError as error:
        raise auth_http_error(error) from error


def require_ready_context(context: AuthContext = Depends(require_session)) -> AuthContext:
    if context.admin.must_change_password:
        raise auth_http_error(AuthError("PASSWORD_CHANGE_REQUIRED", status_code=403))
    return context


def require_ready_admin(context: AuthContext = Depends(require_ready_context)) -> AdminAccount:
    return context.admin
