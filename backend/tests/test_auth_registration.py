from __future__ import annotations

from collections.abc import Iterator

import pytest
from app.core.config import Settings, get_settings
from app.core.security import hash_password, login_throttle
from app.db.session import session_scope
from app.main import app
from app.models import AuthUser
from app.services.auth_service import AuthService
from fastapi.testclient import TestClient
from sqlalchemy import select


@pytest.fixture()
def reg_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        auth_enabled=True,
        registration_enabled=True,
        registration_invite_code="etf2026",
        private_access_token="legacy-machine-token-only",
        auth_username="jovi",
        auth_email="jovi@example.test",
        auth_password_hash=hash_password("correct horse battery staple"),
        auth_session_secret="test-session-secret-that-is-long-and-random",
        auth_session_ttl_minutes=30,
        auth_cookie_secure=False,
        market_provider="mock",
    )


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, reg_settings: Settings) -> Iterator[TestClient]:
    import app.main as main_module

    login_throttle.reset_for_tests()
    app.dependency_overrides[get_settings] = lambda: reg_settings
    monkeypatch.setattr(main_module, "settings", reg_settings)
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_settings, None)
        login_throttle.reset_for_tests()


def test_registration_success_sets_cookies_and_logs_in(client: TestClient) -> None:
    payload = {
        "identifier": "newuser01",
        "email": "newuser01@example.com",
        "password": "valid_password_2026",
        "invite_code": "etf2026",
    }
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["authenticated"] is True
    assert data["identifier"] == "newuser01"
    assert data["role"] == "member"

    # Verify session and csrf cookies set
    assert "fund-session" in response.cookies
    assert "fund-csrf" in response.cookies

    # Verify /api/auth/me resolves the newly logged-in member
    me_resp = client.get("/api/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json() == {
        "authenticated": True,
        "identifier": "newuser01",
        "role": "member",
    }


def test_registration_invalid_invite_code_rejected(client: TestClient) -> None:
    payload = {
        "identifier": "badinvite_user",
        "password": "valid_password_2026",
        "invite_code": "wrong_invite_code",
    }
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 400
    assert "邀请码错误" in response.json()["detail"]

    # Verify user was not created
    with session_scope() as db:
        user = db.scalar(select(AuthUser).where(AuthUser.username == "badinvite_user"))
        assert user is None


def test_registration_duplicate_username_conflict(client: TestClient) -> None:
    payload = {
        "identifier": "duplicate_candidate",
        "password": "valid_password_2026",
        "invite_code": "etf2026",
    }
    first = client.post("/api/auth/register", json=payload)
    assert first.status_code == 201

    second = client.post("/api/auth/register", json=payload)
    assert second.status_code == 409
    assert "已存在" in second.json()["detail"] or "已被注册" in second.json()["detail"]


def test_registration_disabled(client: TestClient, monkeypatch: pytest.MonkeyPatch, reg_settings: Settings) -> None:
    disabled_settings = reg_settings.model_copy(update={"registration_enabled": False})
    app.dependency_overrides[get_settings] = lambda: disabled_settings
    monkeypatch.setattr("app.main.settings", disabled_settings)

    payload = {
        "identifier": "disabled_mode_user",
        "password": "valid_password_2026",
        "invite_code": "etf2026",
    }
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 403
    assert "未开放自主注册" in response.json()["detail"]


def test_registration_validation_constraints(client: TestClient) -> None:
    # Too short password (< 6 chars)
    short_pw = client.post(
        "/api/auth/register",
        json={"identifier": "shortpwuser", "password": "123", "invite_code": "etf2026"},
    )
    assert short_pw.status_code == 422

    # Blank identifier
    blank_id = client.post(
        "/api/auth/register",
        json={"identifier": "   ", "password": "valid_password_2026", "invite_code": "etf2026"},
    )
    assert blank_id.status_code == 422

    # Blank invite code
    blank_code = client.post(
        "/api/auth/register",
        json={"identifier": "validuser", "password": "valid_password_2026", "invite_code": "  "},
    )
    assert blank_code.status_code == 422
