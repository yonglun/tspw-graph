from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.projects.models import Base

from .models import AdminAccount, AdminAuditEvent, AdminLoginThrottle, AdminSession


def normalize_username(value: str) -> str:
    return value.strip().casefold()


class AuthRepository:
    def __init__(
        self,
        engine: Engine,
        clock: Callable[[], datetime] | None = None,
        *,
        max_failures: int = 5,
        lock_seconds: int = 15 * 60,
    ) -> None:
        self.engine = engine
        self._clock = clock or (lambda: datetime.now(UTC))
        self.max_failures = max_failures
        self.lock_seconds = lock_seconds
        self._sessions = sessionmaker(engine, expire_on_commit=False)
        Base.metadata.create_all(engine)

    def now(self) -> datetime:
        value = self._clock()
        return value if value.tzinfo else value.replace(tzinfo=UTC)

    def create_admin(self, username: str, password_hash: str, *, must_change_password: bool) -> AdminAccount:
        cleaned = username.strip()
        account = AdminAccount(
            username=cleaned,
            normalized_username=normalize_username(cleaned),
            password_hash=password_hash,
            must_change_password=must_change_password,
        )
        with self._sessions.begin() as session:
            session.add(account)
        return account

    def get_admin(self, admin_id: str) -> AdminAccount | None:
        with self._sessions() as session:
            return session.get(AdminAccount, admin_id)

    def find_admin_by_username(self, username: str) -> AdminAccount | None:
        with self._sessions() as session:
            return session.scalar(select(AdminAccount).where(AdminAccount.normalized_username == normalize_username(username)))

    def list_admins(self) -> list[AdminAccount]:
        with self._sessions() as session:
            return list(session.scalars(select(AdminAccount).order_by(AdminAccount.normalized_username)))

    def enabled_admin_count(self) -> int:
        with self._sessions() as session:
            return int(session.scalar(select(func.count()).select_from(AdminAccount).where(AdminAccount.enabled.is_(True))) or 0)

    def update_admin(self, admin_id: str, **changes: object) -> AdminAccount:
        allowed = {"username", "normalized_username", "password_hash", "enabled", "must_change_password"}
        with self._sessions.begin() as session:
            account = session.get(AdminAccount, admin_id)
            if account is None:
                raise KeyError(admin_id)
            for key, value in changes.items():
                if key not in allowed:
                    raise ValueError(f"Unsupported admin field: {key}")
                setattr(account, key, value)
            account.updated_at = self.now()
        return account

    def create_session(self, admin_id: str, *, token_hash: str, csrf_token: str, ip_address: str | None, user_agent: str | None, expires_at: datetime) -> AdminSession:
        admin_session = AdminSession(
            admin_id=admin_id,
            token_hash=token_hash,
            csrf_token=csrf_token,
            ip_address=ip_address,
            user_agent=user_agent,
            created_at=self.now(),
            last_seen_at=self.now(),
            expires_at=expires_at,
        )
        with self._sessions.begin() as session:
            session.add(admin_session)
        return admin_session

    def find_session(self, token_hash: str) -> AdminSession | None:
        with self._sessions() as session:
            return session.scalar(select(AdminSession).where(AdminSession.token_hash == token_hash))

    def touch_session(self, session_id: str, *, expires_at: datetime) -> AdminSession:
        with self._sessions.begin() as session:
            value = session.get(AdminSession, session_id)
            if value is None:
                raise KeyError(session_id)
            value.last_seen_at = self.now()
            value.expires_at = expires_at
        return value

    def revoke_session(self, session_id: str) -> None:
        with self._sessions.begin() as session:
            session.execute(delete(AdminSession).where(AdminSession.id == session_id))

    def revoke_admin_sessions(self, admin_id: str, *, except_session_id: str | None = None) -> None:
        statement = delete(AdminSession).where(AdminSession.admin_id == admin_id)
        if except_session_id:
            statement = statement.where(AdminSession.id != except_session_id)
        with self._sessions.begin() as session:
            session.execute(statement)

    def get_login_throttle(self, normalized_username: str, ip_address: str) -> AdminLoginThrottle | None:
        with self._sessions() as session:
            return session.scalar(select(AdminLoginThrottle).where(
                AdminLoginThrottle.normalized_username == normalized_username,
                AdminLoginThrottle.ip_address == ip_address,
            ))

    def record_login_failure(self, normalized_username: str, ip_address: str) -> AdminLoginThrottle:
        now = self.now()
        with self._sessions.begin() as session:
            throttle = session.scalar(select(AdminLoginThrottle).where(
                AdminLoginThrottle.normalized_username == normalized_username,
                AdminLoginThrottle.ip_address == ip_address,
            ))
            if throttle is None:
                throttle = AdminLoginThrottle(normalized_username=normalized_username, ip_address=ip_address)
                session.add(throttle)
            if throttle.locked_until and _aware(throttle.locked_until) <= now:
                throttle.failure_count = 0
                throttle.locked_until = None
            throttle.failure_count += 1
            throttle.updated_at = now
            if throttle.failure_count >= self.max_failures:
                throttle.locked_until = now + timedelta(seconds=self.lock_seconds)
        return throttle

    def clear_login_failures(self, normalized_username: str, ip_address: str) -> None:
        with self._sessions.begin() as session:
            session.execute(delete(AdminLoginThrottle).where(
                AdminLoginThrottle.normalized_username == normalized_username,
                AdminLoginThrottle.ip_address == ip_address,
            ))

    def add_audit_event(self, *, actor: AdminAccount | None, target: AdminAccount | None, action: str, result: str, ip_address: str | None, metadata: dict[str, object]) -> AdminAuditEvent:
        event = AdminAuditEvent(
            actor_admin_id=actor.id if actor else None,
            actor_username=actor.username if actor else None,
            target_admin_id=target.id if target else None,
            target_username=target.username if target else None,
            action=action,
            result=result,
            ip_address=ip_address,
            event_metadata=_sanitize_metadata(metadata),
            created_at=self.now(),
        )
        with self._sessions.begin() as session:
            session.add(event)
        return event

    def list_audit_events(self, *, limit: int = 100) -> list[AdminAuditEvent]:
        with self._sessions() as session:
            return list(session.scalars(select(AdminAuditEvent).order_by(AdminAuditEvent.created_at.desc()).limit(limit)))


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _sanitize_metadata(metadata: dict[str, object]) -> dict[str, object]:
    forbidden = {"password", "password_hash", "cookie", "session_token", "csrf", "csrf_token", "token"}
    return {key: value for key, value in metadata.items() if key.casefold() not in forbidden}
