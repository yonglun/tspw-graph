from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.auth.dependencies import get_auth_service
from app.auth.repository import AuthRepository
from app.auth.router import router
from app.auth.service import AuthService
from app.settings import Settings


def make_client(tmp_path: Path) -> TestClient:
    settings = Settings(sqlite_url=f"sqlite:///{tmp_path / 'auth.db'}")
    service = AuthService(AuthRepository(create_engine(settings.sqlite_url)), settings)
    service.bootstrap_default_admin()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_auth_service] = lambda: service
    return TestClient(app)


def test_login_sets_http_only_cookie_and_returns_csrf(tmp_path):
    client = make_client(tmp_path)
    response = client.post("/api/auth/login", json={"username": "admin", "password": "Pass@word1"})
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"]
    assert response.json()["must_change_password"] is True
    assert response.json()["csrf_token"]


def test_change_password_requires_matching_csrf(tmp_path):
    client = make_client(tmp_path)
    login = client.post("/api/auth/login", json={"username": "admin", "password": "Pass@word1"})
    missing = client.post("/api/auth/change-password", json={"current_password": "Pass@word1", "new_password": "Better@Pass2"})
    assert missing.status_code == 403
    assert missing.json()["detail"]["code"] == "CSRF_VALIDATION_FAILED"
    changed = client.post(
        "/api/auth/change-password",
        headers={"X-CSRF-Token": login.json()["csrf_token"]},
        json={"current_password": "Pass@word1", "new_password": "Better@Pass2"},
    )
    assert changed.status_code == 200
    assert changed.json()["must_change_password"] is False
