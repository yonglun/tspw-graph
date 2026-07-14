from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from .dependencies import auth_http_error, get_auth_service, require_session
from .schemas import AuthContext, ChangePasswordRequest, LoginRequest, SessionResponse
from .service import AuthError, AuthService


router = APIRouter(prefix="/api/auth", tags=["auth"])


def _client_ip(request: Request, service: AuthService) -> str:
    if service.settings.auth_trust_forwarded_ip:
        trusted = request.headers.get("X-Real-IP", "").strip()
        if trusted:
            return trusted
    return request.client.host if request.client else "unknown"


def _reject_cross_origin(request: Request) -> None:
    origin = request.headers.get("Origin")
    if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
        raise auth_http_error(AuthError("CROSS_ORIGIN_LOGIN_REJECTED", status_code=403))


@router.post("/login", response_model=SessionResponse)
def login(payload: LoginRequest, request: Request, response: Response, service: AuthService = Depends(get_auth_service)) -> SessionResponse:
    _reject_cross_origin(request)
    try:
        result = service.login(payload.username, payload.password, _client_ip(request, service), request.headers.get("User-Agent"))
    except AuthError as error:
        raise auth_http_error(error) from error
    response.set_cookie(
        service.settings.auth_cookie_name,
        result.session_token,
        max_age=service.settings.auth_session_idle_seconds,
        httponly=True,
        secure=service.settings.auth_cookie_secure,
        samesite="strict",
        path="/",
    )
    return result.response


@router.get("/session", response_model=SessionResponse)
def session(context: AuthContext = Depends(require_session)) -> SessionResponse:
    return AuthService._response(context.admin, context.session.csrf_token)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, context: AuthContext = Depends(require_session), service: AuthService = Depends(get_auth_service)) -> Response:
    service.logout(context, _client_ip(request, service))
    response.delete_cookie(service.settings.auth_cookie_name, path="/")
    response.status_code = 204
    return response


@router.post("/change-password", response_model=SessionResponse)
def change_password(payload: ChangePasswordRequest, request: Request, context: AuthContext = Depends(require_session), service: AuthService = Depends(get_auth_service)) -> SessionResponse:
    try:
        return service.change_password(context, payload.current_password, payload.new_password, _client_ip(request, service))
    except AuthError as error:
        raise auth_http_error(error) from error
