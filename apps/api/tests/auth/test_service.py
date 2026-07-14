from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.auth.repository import AuthRepository
from app.auth.service import AuthError, AuthService
from app.settings import Settings


class Clock:
    def __init__(self):
        self.value = datetime(2026, 7, 14, tzinfo=UTC)

    def __call__(self):
        return self.value

    def advance(self, delta):
        self.value += delta


@pytest.fixture
def setup_service():
    clock = Clock()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    settings = Settings(sqlite_url="sqlite://", auth_session_idle_seconds=8 * 60 * 60)
    repository = AuthRepository(engine, clock=clock, max_failures=5, lock_seconds=900)
    service = AuthService(repository, settings)
    return service, repository, clock


def test_bootstrap_is_idempotent_and_requires_password_change(setup_service):
    service, repository, _ = setup_service
    first = service.bootstrap_default_admin()
    second = service.bootstrap_default_admin()
    assert first.id == second.id
    assert len(repository.list_admins()) == 1
    assert first.must_change_password is True


def test_fifth_failure_locks_username_and_ip_for_fifteen_minutes(setup_service):
    service, _, _ = setup_service
    service.bootstrap_default_admin()
    for _ in range(4):
        with pytest.raises(AuthError, match="INVALID_CREDENTIALS"):
            service.login("admin", "wrong", "10.0.0.1", "pytest")
    with pytest.raises(AuthError, match="ACCOUNT_LOCKED") as locked:
        service.login("admin", "wrong", "10.0.0.1", "pytest")
    assert locked.value.retry_after_seconds == 900


def test_session_expires_after_eight_idle_hours(setup_service):
    service, _, clock = setup_service
    service.bootstrap_default_admin()
    login = service.login("admin", "Pass@word1", "127.0.0.1", "pytest")
    clock.advance(timedelta(hours=8, seconds=1))
    with pytest.raises(AuthError, match="AUTHENTICATION_REQUIRED"):
        service.authenticate(login.session_token)


def ready_context(service: AuthService):
    service.bootstrap_default_admin()
    login = service.login("admin", "Pass@word1", "127.0.0.1", "pytest")
    context = service.authenticate(login.session_token)
    service.change_password(context, "Pass@word1", "Better@Pass2")
    return service.authenticate(login.session_token)


def test_cannot_disable_self_and_can_disable_another_admin(setup_service):
    service, repository, _ = setup_service
    context = ready_context(service)
    with pytest.raises(AuthError, match="CANNOT_DISABLE_SELF"):
        service.disable_admin(context, context.admin.id, "127.0.0.1")
    second = service.create_admin(context, "second", "Second@Pass2", "127.0.0.1")
    service.disable_admin(context, second.id, "127.0.0.1")
    assert repository.get_admin(second.id).enabled is False


def test_reset_password_revokes_sessions_and_forces_change(setup_service):
    service, repository, _ = setup_service
    context = ready_context(service)
    target = service.create_admin(context, "second", "Second@Pass2", "127.0.0.1")
    target_login = service.login("second", "Second@Pass2", "127.0.0.2", "pytest")
    service.reset_password(context, target.id, "Temporary@3", "127.0.0.1")
    with pytest.raises(AuthError, match="AUTHENTICATION_REQUIRED"):
        service.authenticate(target_login.session_token)
    assert repository.get_admin(target.id).must_change_password is True
