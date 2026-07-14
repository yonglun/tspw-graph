from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.settings import Settings

from .repository import AuthRepository, normalize_username
from .schemas import AdminSummary, AuthContext, SessionResponse
from .security import PasswordPolicy, PasswordSecurity, csrf_matches, hash_session_token, new_token


class AuthError(Exception):
    def __init__(self, code: str, *, status_code: int = 400, retry_after_seconds: int | None = None, details: dict[str, object] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds
        self.details = details or {}


@dataclass(frozen=True)
class LoginResult:
    session_token: str
    response: SessionResponse


class AuthService:
    def __init__(self, repository: AuthRepository, settings: Settings, password_security: PasswordSecurity | None = None) -> None:
        self.repository = repository
        self.settings = settings
        self.password_security = password_security or PasswordSecurity()
        self._dummy_hash = self.password_security.hash("Dummy@Password1")

    def bootstrap_default_admin(self):
        admins = self.repository.list_admins()
        if admins:
            return admins[0]
        failures = PasswordPolicy.validate(self.settings.auth_bootstrap_password)
        if failures:
            raise RuntimeError(f"Bootstrap password violates policy: {','.join(failures)}")
        return self.repository.create_admin(
            self.settings.auth_bootstrap_username,
            self.password_security.hash(self.settings.auth_bootstrap_password),
            must_change_password=True,
        )

    def login(self, username: str, password: str, ip_address: str, user_agent: str | None) -> LoginResult:
        normalized = normalize_username(username)
        throttle = self.repository.get_login_throttle(normalized, ip_address)
        now = self.repository.now()
        if throttle and throttle.locked_until and _aware(throttle.locked_until) > now:
            retry = max(1, int((_aware(throttle.locked_until) - now).total_seconds()))
            raise AuthError("ACCOUNT_LOCKED", status_code=429, retry_after_seconds=retry)

        admin = self.repository.find_admin_by_username(username)
        valid = self.password_security.verify(admin.password_hash if admin else self._dummy_hash, password)
        if admin is None or not admin.enabled or not valid:
            failed = self.repository.record_login_failure(normalized, ip_address)
            if failed.locked_until and _aware(failed.locked_until) > now:
                retry = max(1, int((_aware(failed.locked_until) - now).total_seconds()))
                self.repository.add_audit_event(actor=None, target=admin, action="LOGIN", result="LOCKED", ip_address=ip_address, metadata={"username": username.strip()})
                raise AuthError("ACCOUNT_LOCKED", status_code=429, retry_after_seconds=retry)
            self.repository.add_audit_event(actor=None, target=admin, action="LOGIN", result="REJECTED", ip_address=ip_address, metadata={"username": username.strip()})
            raise AuthError("INVALID_CREDENTIALS", status_code=401)

        self.repository.clear_login_failures(normalized, ip_address)
        raw_token = new_token()
        csrf_token = new_token()
        session = self.repository.create_session(
            admin.id,
            token_hash=hash_session_token(raw_token),
            csrf_token=csrf_token,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=now + timedelta(seconds=self.settings.auth_session_idle_seconds),
        )
        self.repository.add_audit_event(actor=admin, target=admin, action="LOGIN", result="SUCCESS", ip_address=ip_address, metadata={"session_id": session.id})
        return LoginResult(raw_token, self._response(admin, session.csrf_token))

    def authenticate(self, session_token: str | None) -> AuthContext:
        if not session_token:
            raise AuthError("AUTHENTICATION_REQUIRED", status_code=401)
        session = self.repository.find_session(hash_session_token(session_token))
        if session is None:
            raise AuthError("AUTHENTICATION_REQUIRED", status_code=401)
        now = self.repository.now()
        if _aware(session.expires_at) <= now:
            self.repository.revoke_session(session.id)
            raise AuthError("AUTHENTICATION_REQUIRED", status_code=401)
        admin = self.repository.get_admin(session.admin_id)
        if admin is None or not admin.enabled:
            self.repository.revoke_session(session.id)
            raise AuthError("AUTHENTICATION_REQUIRED", status_code=401)
        session = self.repository.touch_session(
            session.id,
            expires_at=now + timedelta(seconds=self.settings.auth_session_idle_seconds),
        )
        return AuthContext(admin=admin, session=session)

    def verify_csrf(self, context: AuthContext, presented: str) -> None:
        if not csrf_matches(context.session.csrf_token, presented):
            raise AuthError("CSRF_VALIDATION_FAILED", status_code=403)

    def logout(self, context: AuthContext, ip_address: str | None = None) -> None:
        self.repository.revoke_session(context.session.id)
        self.repository.add_audit_event(actor=context.admin, target=context.admin, action="LOGOUT", result="SUCCESS", ip_address=ip_address, metadata={})

    def change_password(self, context: AuthContext, current_password: str, new_password: str, ip_address: str | None = None) -> SessionResponse:
        if not self.password_security.verify(context.admin.password_hash, current_password):
            self.repository.add_audit_event(actor=context.admin, target=context.admin, action="PASSWORD_CHANGE", result="REJECTED", ip_address=ip_address, metadata={"reason": "CURRENT_PASSWORD_INVALID"})
            raise AuthError("CURRENT_PASSWORD_INVALID", status_code=400)
        failures = PasswordPolicy.validate(new_password)
        if failures:
            raise AuthError("PASSWORD_POLICY_VIOLATION", status_code=422, details={"violations": failures})
        account = self.repository.update_admin(
            context.admin.id,
            password_hash=self.password_security.hash(new_password),
            must_change_password=False,
        )
        self.repository.revoke_admin_sessions(account.id, except_session_id=context.session.id)
        self.repository.add_audit_event(actor=account, target=account, action="PASSWORD_CHANGE", result="SUCCESS", ip_address=ip_address, metadata={})
        return self._response(account, context.session.csrf_token)

    @staticmethod
    def _response(admin, csrf_token: str) -> SessionResponse:
        return SessionResponse(
            admin=AdminSummary.from_account(admin),
            must_change_password=admin.must_change_password,
            csrf_token=csrf_token,
        )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
