from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, Field

from .models import AdminAccount, AdminSession


@dataclass(frozen=True)
class AuthContext:
    admin: AdminAccount
    session: AdminSession


class AdminSummary(BaseModel):
    id: str
    username: str
    is_enabled: bool
    must_change_password: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_account(cls, account: AdminAccount) -> "AdminSummary":
        return cls(
            id=account.id,
            username=account.username,
            is_enabled=account.enabled,
            must_change_password=account.must_change_password,
            created_at=account.created_at,
            updated_at=account.updated_at,
        )


class SessionResponse(BaseModel):
    admin: AdminSummary
    must_change_password: bool
    csrf_token: str


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=1024)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=1, max_length=1024)


class AdminCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    temporary_password: str = Field(min_length=1, max_length=1024)


class AdminUpdateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)


class AdminResetPasswordRequest(BaseModel):
    temporary_password: str = Field(min_length=1, max_length=1024)


class AuditEventResponse(BaseModel):
    id: str
    actor_username: str | None
    target_username: str | None
    action: str
    result: str
    ip_address: str | None
    metadata: dict[str, object]
    created_at: datetime


class AuditPage(BaseModel):
    items: list[AuditEventResponse]
    next_cursor: str | None = None
