"""A-U1: self-service changes use real database sessions and never claim verification."""
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import AuthUser
from app.services.auth_service import AuthService
from app.workspace.models import WorkspaceBridgeDevice, WorkspacePreference

PASSWORD = "test-only-admin-password"
NEW_PASSWORD = "test-only-new-password"


@pytest.fixture()
def account_case(monkeypatch) -> Iterator:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    settings = Settings(_env_file=None, app_env="test", auth_enabled=True,
                        auth_cookie_secure=False, auto_create_schema=False, market_provider="mock")
    def db_dependency():
        with factory() as db:
            yield db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db] = db_dependency
    monkeypatch.setattr("app.main.settings", settings)
    with factory() as db:
        svc = AuthService()
        admin = svc.create_user(db, username="account-admin", password=PASSWORD, role="admin")
        user = svc.create_user(db, username="account-member", password=PASSWORD, email="private@example.test")
        second = svc.create_user(db, username="account-other", password=PASSWORD)
        issued = svc.create_session(db, user)
        other = svc.create_session(db, user)
        admin_session = svc.create_session(db, admin)
        ids = {"user": user.id, "other": second.id, "admin": admin.id}
        db.commit()
    client = TestClient(app)
    client.cookies.set("fund-session", issued.session_token)
    client.cookies.set("fund-csrf", issued.csrf_token)
    headers = {"X-CSRF-Token": issued.csrf_token}
    try:
        yield client, factory, settings, headers, ids, other, admin_session
    finally:
        client.close()
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def test_profile_reads_only_current_user_and_never_claims_verified_contact(account_case):
    client, _, _, _, ids, *_ = account_case
    r = client.get("/api/workspace/account")
    assert r.status_code == 200
    value = r.json()
    assert value["identifier"] == "account-member"
    assert value["email"]["state"] == "recorded_unverified"
    assert value["email"]["masked"] == "p***@example.test"
    assert value["capabilities"]["email_verification"] is False
    assert value["capabilities"]["sms_verification"] is False
    assert value["capabilities"]["wechat_oauth"] is False
    assert value["capabilities"]["permanent_erasure"] is False
    assert "private@example.test" not in r.text
    assert PASSWORD not in r.text and "password_hash" not in r.text
    assert "no-store" in r.headers["cache-control"]


@pytest.mark.parametrize("mode", ["anonymous", "legacy", "no-auth"])
def test_personal_account_requires_database_user_even_in_demo(account_case, mode):
    client, _, settings, _, *_ = account_case
    client.cookies.clear()
    if mode == "legacy":
        settings.private_access_token = "legacy-machine-token-only"
        client.headers["Authorization"] = "Bearer " + settings.private_access_token
    if mode == "no-auth":
        settings.auth_enabled = False
    assert client.get("/api/workspace/account").status_code == 401


def test_display_name_is_persisted_without_changing_login_or_other_account(account_case):
    client, factory, _, headers, ids, *_ = account_case
    r = client.patch("/api/workspace/account/profile", headers=headers, json={"display_name": "研究员 小乔"})
    assert r.status_code == 200
    assert client.get("/api/workspace/account").json()["display_name"] == "研究员 小乔"
    with factory() as db:
        assert db.get(AuthUser, ids["user"]).username == "account-member"
        assert db.get(AuthUser, ids["other"]).username == "account-other"


def test_profile_rejects_csrf_and_mass_assignment(account_case):
    client, _, _, headers, *_ = account_case
    assert client.patch("/api/workspace/account/profile", json={"display_name": "other"}).status_code == 403
    r = client.patch("/api/workspace/account/profile", headers=headers,
                     json={"display_name": "other", "role": "admin", "email_verified": True})
    assert r.status_code == 422
    assert "input" not in r.json()


@pytest.mark.parametrize("name", ["", "  ", "x" * 49, "bad\x00name", "bad\u202ename"])
def test_invalid_display_name_rejected(account_case, name):
    client, _, _, headers, *_ = account_case
    assert client.patch("/api/workspace/account/profile", headers=headers, json={"display_name": name}).status_code == 422


def test_wrong_current_password_does_not_change_or_revoke(account_case):
    client, factory, _, headers, ids, other, _ = account_case
    r = client.put("/api/workspace/account/password", headers=headers,
                   json={"current_password": "wrong-fixture", "new_password": NEW_PASSWORD})
    assert r.status_code == 403
    assert r.json()["detail"] == "current_password_invalid"
    with factory() as db:
        assert AuthService().verify_password(PASSWORD, db.get(AuthUser, ids["user"]).password_hash)
        assert AuthService().resolve_session(db, other.session_token)
    assert "wrong-fixture" not in r.text


def test_password_change_revokes_all_sessions_and_requires_new_login(account_case):
    client, factory, _, headers, ids, other, _ = account_case
    r = client.put("/api/workspace/account/password", headers=headers,
                   json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert r.status_code == 200
    assert r.json()["reauthenticate"] is True
    with factory() as db:
        assert AuthService().resolve_session(db, other.session_token) is None
        user = db.get(AuthUser, ids["user"])
        assert not AuthService().verify_password(PASSWORD, user.password_hash)
        assert AuthService().verify_password(NEW_PASSWORD, user.password_hash)
    assert client.get("/api/workspace/account").status_code == 401
    assert client.post("/api/auth/login", json={"identifier": "account-member", "password": NEW_PASSWORD}).status_code == 200


def test_password_validation_never_echoes_credentials(account_case):
    client, _, _, headers, *_ = account_case
    r = client.put("/api/workspace/account/password", headers=headers,
                   json={"current_password": PASSWORD, "new_password": "short"})
    assert r.status_code == 422
    assert PASSWORD not in r.text and "short" not in r.text
    assert "no-store" in r.headers["cache-control"]


def test_sensitive_attempt_limit_is_persisted_in_database(account_case):
    client, _, _, headers, *_ = account_case
    for _ in range(5):
        assert client.put("/api/workspace/account/password", headers=headers,
                          json={"current_password": "wrong", "new_password": NEW_PASSWORD}).status_code == 403
    r = client.put("/api/workspace/account/password", headers=headers,
                   json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert r.status_code == 429


def test_closure_requires_explicit_retention_ack_and_confirmation(account_case):
    client, _, _, headers, *_ = account_case
    r = client.post("/api/workspace/account/closure", headers=headers,
                    json={"current_password": PASSWORD, "confirmation": "wrong", "acknowledge_retention": True})
    assert r.status_code == 422
    assert client.get("/api/workspace/account").status_code == 200


def test_closure_disables_access_preserves_data_and_revokes_devices(account_case):
    client, factory, _, headers, ids, other, _ = account_case
    with factory() as db:
        db.add(WorkspaceBridgeDevice(device_id="a" * 32, user_id=ids["user"], owner_scope=f'user:{ids["user"]}',
                                     label="fixture device", status="paired"))
        db.add(WorkspacePreference(owner_scope=f'account:data:{ids["user"]}', user_id=ids["user"], settings_json={"preserve": True}))
        db.commit()
    r = client.post("/api/workspace/account/closure", headers=headers,
                    json={"current_password": PASSWORD, "confirmation": "注销当前账户", "acknowledge_retention": True})
    assert r.status_code == 200
    assert r.json()["data_erased"] is False
    with factory() as db:
        assert db.get(AuthUser, ids["user"]).status == "disabled"
        assert db.get(AuthUser, ids["other"]).status == "active"
        assert db.get(WorkspaceBridgeDevice, "a" * 32).status == "revoked"
        assert db.get(WorkspacePreference, f'account:data:{ids["user"]}').settings_json == {"preserve": True}
        assert AuthService().resolve_session(db, other.session_token) is None


def test_last_admin_cannot_close(account_case):
    client, _, _, _, _, _, admin_session = account_case
    client.cookies.set("fund-session", admin_session.session_token)
    client.cookies.set("fund-csrf", admin_session.csrf_token)
    r = client.post("/api/workspace/account/closure", headers={"X-CSRF-Token": admin_session.csrf_token},
                    json={"current_password": PASSWORD, "confirmation": "注销当前账户", "acknowledge_retention": True})
    assert r.status_code == 409
    assert r.json()["detail"] == "last_active_admin_protected"
