from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from app.auth.repository import AuthRepository, LastEnabledAdminError
from app.auth.security import hash_session_token


@pytest.fixture
def repository() -> AuthRepository:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    return AuthRepository(engine, clock=lambda: datetime(2026, 7, 14, tzinfo=UTC))


def test_admin_username_is_case_insensitively_unique(repository: AuthRepository):
    repository.create_admin("Admin", "hash-1", must_change_password=True)
    with pytest.raises(IntegrityError):
        repository.create_admin("admin", "hash-2", must_change_password=True)


def test_repository_never_saves_raw_session_token(repository: AuthRepository):
    admin = repository.create_admin("admin", "hash", must_change_password=True)
    repository.create_session(
        admin.id,
        token_hash=hash_session_token("raw-token"),
        csrf_token="csrf-value",
        ip_address="127.0.0.1",
        user_agent="pytest",
        expires_at=repository.now() + timedelta(hours=8),
    )
    session = repository.find_session(hash_session_token("raw-token"))
    assert session is not None
    assert session.token_hash != "raw-token"
    assert session.csrf_token == "csrf-value"


def test_audit_metadata_drops_secrets(repository: AuthRepository):
    admin = repository.create_admin("admin", "hash", must_change_password=True)
    event = repository.add_audit_event(
        actor=admin,
        target=admin,
        action="PASSWORD_CHANGED",
        result="SUCCESS",
        ip_address="127.0.0.1",
        metadata={"reason": "user", "password": "secret", "csrf_token": "secret"},
    )
    assert event.event_metadata == {"reason": "user"}


def test_disabling_the_last_enabled_admin_is_rejected_in_the_write_transaction(
    repository: AuthRepository,
):
    admin = repository.create_admin("admin", "hash", must_change_password=True)

    with pytest.raises(LastEnabledAdminError):
        repository.disable_admin(admin.id)

    assert repository.get_admin(admin.id).enabled is True
