from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from .dependencies import auth_http_error, get_auth_service, require_ready_context
from .router import _client_ip
from .schemas import AdminCreateRequest, AdminResetPasswordRequest, AdminSummary, AdminUpdateRequest, AuditPage, AuthContext
from .service import AuthError, AuthService


router = APIRouter(prefix="/api", tags=["administrators"])


def _run(call):
    try:
        return call()
    except AuthError as error:
        raise auth_http_error(error) from error


@router.get("/admins", response_model=list[AdminSummary])
def list_admins(context: AuthContext = Depends(require_ready_context), service: AuthService = Depends(get_auth_service)):
    return service.list_admins(context)


@router.post("/admins", response_model=AdminSummary, status_code=201)
def create_admin(payload: AdminCreateRequest, request: Request, context: AuthContext = Depends(require_ready_context), service: AuthService = Depends(get_auth_service)):
    return _run(lambda: service.create_admin(context, payload.username, payload.temporary_password, _client_ip(request, service)))


@router.patch("/admins/{admin_id}", response_model=AdminSummary)
def rename_admin(admin_id: str, payload: AdminUpdateRequest, request: Request, context: AuthContext = Depends(require_ready_context), service: AuthService = Depends(get_auth_service)):
    return _run(lambda: service.rename_admin(context, admin_id, payload.username, _client_ip(request, service)))


@router.post("/admins/{admin_id}/enable", response_model=AdminSummary)
def enable_admin(admin_id: str, request: Request, context: AuthContext = Depends(require_ready_context), service: AuthService = Depends(get_auth_service)):
    return _run(lambda: service.enable_admin(context, admin_id, _client_ip(request, service)))


@router.post("/admins/{admin_id}/disable", response_model=AdminSummary)
def disable_admin(admin_id: str, request: Request, context: AuthContext = Depends(require_ready_context), service: AuthService = Depends(get_auth_service)):
    return _run(lambda: service.disable_admin(context, admin_id, _client_ip(request, service)))


@router.post("/admins/{admin_id}/reset-password", response_model=AdminSummary)
def reset_password(admin_id: str, payload: AdminResetPasswordRequest, request: Request, context: AuthContext = Depends(require_ready_context), service: AuthService = Depends(get_auth_service)):
    return _run(lambda: service.reset_password(context, admin_id, payload.temporary_password, _client_ip(request, service)))


@router.get("/admin-audit-events", response_model=AuditPage)
def audit_events(limit: int = Query(100, ge=1, le=200), cursor: str | None = None, context: AuthContext = Depends(require_ready_context), service: AuthService = Depends(get_auth_service)):
    return service.list_audit_events(context, limit, cursor)
