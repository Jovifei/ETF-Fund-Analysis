from __future__ import annotations

import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import pytest
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db, session_scope
from app.main import app
from app.models import (
    AuthSession,
    AuthUser,
    EventLog,
    Holding,
    HoldingImportCandidate,
    HoldingImportSession,
    Instrument,
    ProviderAudit,
    ReportArtifact,
    SignalSnapshot,
    TaskRun,
)
from app.ocr.contracts import OCRLine
from app.ocr.fake import FakeOCRBackend
from app.services.auth_service import AuthService
from app.services.holding_import_service import HoldingImportNotFound, HoldingImportService
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import sessionmaker
from typer.testing import CliRunner


@pytest.fixture()
def multi_user_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        auth_enabled=True,
        auth_cookie_secure=False,
        auth_session_secret="test-session-secret-that-is-long-and-random",
        auth_session_ttl_minutes=30,
        private_access_token="legacy-machine-token-only",
        market_provider="mock",
    )


@pytest.fixture()
def two_users():
    service = AuthService()
    suffix = uuid4().hex
    with session_scope() as db:
        first = service.create_user(
            db, username=f"owner-one-{suffix}", password="owner one password", role="admin"
        )
        second = service.create_user(db, username=f"owner-two-{suffix}", password="owner two password")
        return {
            "first_id": first.id,
            "first_username": first.username,
            "second_id": second.id,
            "second_username": second.username,
        }


def _client_for_user(settings: Settings, user_id: int) -> TestClient:
    with session_scope() as db:
        user = db.get(AuthUser, user_id)
        issued = AuthService().create_session(db, user)
    client = TestClient(app)
    client.cookies.set("fund-session", issued.session_token)
    client.cookies.set("fund-csrf", issued.csrf_token)
    return client


def _png_upload() -> bytes:
    payload = io.BytesIO()
    Image.new("RGB", (4, 3), color=(25, 80, 120)).save(payload, format="PNG")
    return payload.getvalue()


def _cleanup_ocr_test_rows(settings: Settings, user_ids: tuple[int, ...]) -> None:
    """Remove only the users and ownership rows created by the OCR test.

    This module uses a session-scoped SQLite database, so the two user fixture
    rows must be explicitly removed after this test.  Delete children first to
    honor the restrictive user foreign keys and preserve all bootstrap/shared
    rows belonging to other tests.
    """
    storage = HoldingImportService(settings)
    with session_scope() as db:
        import_sessions = db.scalars(
            select(HoldingImportSession).where(HoldingImportSession.user_id.in_(user_ids))
        ).all()
        for imported in import_sessions:
            # Confirm/cancel normally do this already; this covers assertion
            # failures after upload while retaining the exact storage key.
            storage._remove_storage(imported.storage_key)

        import_session_ids = [imported.id for imported in import_sessions]
        if import_session_ids:
            db.execute(
                delete(HoldingImportCandidate).where(
                    HoldingImportCandidate.session_id.in_(import_session_ids)
                )
            )
        db.execute(delete(Holding).where(Holding.user_id.in_(user_ids)))
        db.execute(delete(HoldingImportSession).where(HoldingImportSession.id.in_(import_session_ids)))
        db.execute(delete(AuthSession).where(AuthSession.user_id.in_(user_ids)))
        db.execute(delete(AuthUser).where(AuthUser.id.in_(user_ids)))


def test_db_login_me_and_logout_use_revocable_database_session(
    monkeypatch: pytest.MonkeyPatch, multi_user_settings: Settings, two_users
) -> None:
    import app.main as main_module

    app.dependency_overrides[get_settings] = lambda: multi_user_settings
    monkeypatch.setattr(main_module, "settings", multi_user_settings)
    try:
        with TestClient(app) as client:
            login = client.post(
                "/api/auth/login",
                json={"identifier": two_users["first_username"], "password": "owner one password"},
            )
            assert login.status_code == 200, login.text
            assert login.json() == {"authenticated": True, "identifier": two_users["first_username"], "role": "admin"}
            assert client.get("/api/auth/me").json() == {
                "authenticated": True,
                "identifier": two_users["first_username"],
                "role": "admin",
            }
            logout = client.post("/api/auth/logout", headers={"X-CSRF-Token": client.cookies.get("fund-csrf")})
            assert logout.status_code == 200
            assert client.get("/api/auth/me").json() == {"authenticated": False, "identifier": None, "role": None}
            with session_scope() as db:
                assert db.scalar(select(AuthSession).where(AuthSession.revoked_at.is_not(None))) is not None
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_user_holdings_are_independent_and_legacy_bearer_cannot_write(
    monkeypatch: pytest.MonkeyPatch, multi_user_settings: Settings, two_users, bootstrapped
) -> None:
    import app.main as main_module

    app.dependency_overrides[get_settings] = lambda: multi_user_settings
    monkeypatch.setattr(main_module, "settings", multi_user_settings)
    first_client = _client_for_user(multi_user_settings, two_users["first_id"])
    second_client = _client_for_user(multi_user_settings, two_users["second_id"])
    payload_one = {"ts_code": "510300.SH", "shares": 100, "cost_price": 4.1}
    payload_two = {"ts_code": "510300.SH", "shares": 200, "cost_price": 4.2}
    try:
        assert first_client.get("/api/instruments", headers={"Authorization": "Bearer legacy-machine-token-only"}).status_code == 401
        legacy_write = first_client.put(
            "/api/holdings/510300.SH",
            json=payload_one,
            headers={"Authorization": "Bearer legacy-machine-token-only"},
        )
        assert legacy_write.status_code == 401
        assert first_client.put(
            "/api/holdings/510300.SH",
            json=payload_one,
            headers={"X-CSRF-Token": first_client.cookies.get("fund-csrf")},
        ).status_code == 200
        assert second_client.put(
            "/api/holdings/510300.SH",
            json=payload_two,
            headers={"X-CSRF-Token": second_client.cookies.get("fund-csrf")},
        ).status_code == 200
        first_rows = first_client.get("/api/holdings").json()
        second_rows = second_client.get("/api/holdings").json()
        assert [(row["ts_code"], row["shares"]) for row in first_rows] == [("510300.SH", 100.0)]
        assert [(row["ts_code"], row["shares"]) for row in second_rows] == [("510300.SH", 200.0)]
        with session_scope() as db:
            instrument = db.scalar(select(Instrument).where(Instrument.ts_code == "510300.SH"))
            assert instrument is not None
            assert db.scalars(select(Holding).where(Holding.instrument_id == instrument.id)).all()
    finally:
        first_client.close()
        second_client.close()
        app.dependency_overrides.pop(get_settings, None)


def test_global_mutations_require_an_active_admin_session(
    monkeypatch: pytest.MonkeyPatch, multi_user_settings: Settings, two_users, bootstrapped
) -> None:
    """A member (and a legacy read token) must never reach global controls."""
    import app.main as main_module
    from app.services.demo_service import DemoService

    app.dependency_overrides[get_settings] = lambda: multi_user_settings
    monkeypatch.setattr(main_module, "settings", multi_user_settings)
    monkeypatch.setattr(DemoService, "load", lambda self: {"status": "ok"})
    admin_client = _client_for_user(multi_user_settings, two_users["first_id"])
    member_client = _client_for_user(multi_user_settings, two_users["second_id"])
    try:
        assert TestClient(app).post("/api/demo/load").status_code == 401
        assert TestClient(app).post(
            "/api/demo/load", headers={"Authorization": "Bearer legacy-machine-token-only"}
        ).status_code == 401
        assert member_client.post(
            "/api/demo/load", headers={"X-CSRF-Token": member_client.cookies.get("fund-csrf")}
        ).status_code == 403
        response = admin_client.post(
            "/api/demo/load", headers={"X-CSRF-Token": admin_client.cookies.get("fund-csrf")}
        )
        assert response.status_code == 200
    finally:
        admin_client.close()
        member_client.close()
        app.dependency_overrides.pop(get_settings, None)


def test_holding_import_service_hides_another_users_session(db_session, two_users, tmp_path) -> None:
    session = HoldingImportSession(
        user_id=two_users["first_id"],
        session_id="a" * 32,
        status="ready",
        image_sha256="b" * 64,
        detected_mime="image/png",
        image_bytes=1,
        image_width=1,
        image_height=1,
        ocr_mode="disabled",
        ocr_backend="test",
        ocr_model="test",
        ocr_version="test",
        candidate_count=0,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    db_session.add(session)
    db_session.flush()

    service = HoldingImportService(Settings(_env_file=None, OCR_TRANSIENT_ROOT=tmp_path))
    with pytest.raises(HoldingImportNotFound):
        service.get(db_session, session.session_id, user_id=two_users["second_id"])


def test_authenticated_http_ocr_upload_releases_auth_transaction_and_keeps_owner_filtering(
    monkeypatch: pytest.MonkeyPatch, multi_user_settings: Settings, two_users, tmp_path, bootstrapped
) -> None:
    """A database-cookie authentication read must not poison OCR's isolated write boundary."""
    import app.main as main_module
    from app.services import holding_import_service

    settings = multi_user_settings.model_copy(
        update={"ocr_transient_root": tmp_path, "ocr_cloud_review_enabled": True}
    )
    app.dependency_overrides[get_settings] = lambda: settings
    monkeypatch.setattr(main_module, "settings", settings)
    monkeypatch.setattr(
        holding_import_service,
        "get_default_ocr_backend",
        lambda _settings: FakeOCRBackend(
            lines=(OCRLine(text="510300.SH 100 4.1", confidence=0.99, box=None),)
        ),
    )
    owner_client = None
    other_client = None
    try:
        owner_client = _client_for_user(settings, two_users["first_id"])
        other_client = _client_for_user(settings, two_users["second_id"])
        upload = owner_client.post(
            "/api/holding-imports",
            files={"file": ("holdings.png", _png_upload(), "image/png")},
            headers={"X-CSRF-Token": owner_client.cookies.get("fund-csrf")},
        )
        assert upload.status_code == 201, upload.text
        imported = upload.json()
        session_id = imported["session_id"]
        assert owner_client.get(f"/api/holding-imports/{session_id}").status_code == 200
        assert other_client.get(f"/api/holding-imports/{session_id}").status_code == 404
        candidate_id = imported["candidates"][0]["id"]
        edit = owner_client.patch(
            f"/api/holding-imports/{session_id}/candidates/{candidate_id}",
            json={"selected_code": "510300.SH"},
            headers={"X-CSRF-Token": owner_client.cookies.get("fund-csrf")},
        )
        assert edit.status_code == 200, edit.text
        consent = owner_client.post(
            f"/api/holding-imports/{session_id}/cloud-consent",
            json={"consent": False},
            headers={"X-CSRF-Token": owner_client.cookies.get("fund-csrf")},
        )
        assert consent.status_code == 200, consent.text
        confirmed = owner_client.post(
            f"/api/holding-imports/{session_id}/confirm",
            headers={"X-CSRF-Token": owner_client.cookies.get("fund-csrf")},
        )
        assert confirmed.status_code == 200, confirmed.text

        cancellable = owner_client.post(
            "/api/holding-imports",
            files={"file": ("holdings.png", _png_upload(), "image/png")},
            headers={"X-CSRF-Token": owner_client.cookies.get("fund-csrf")},
        )
        assert cancellable.status_code == 201, cancellable.text
        cancelled = owner_client.post(
            f"/api/holding-imports/{cancellable.json()['session_id']}/cancel",
            headers={"X-CSRF-Token": owner_client.cookies.get("fund-csrf")},
        )
        assert cancelled.status_code == 200, cancelled.text
    finally:
        if owner_client is not None:
            owner_client.close()
        if other_client is not None:
            other_client.close()
        app.dependency_overrides.pop(get_settings, None)
        _cleanup_ocr_test_rows(
            settings, (two_users["first_id"], two_users["second_id"])
        )


def test_member_bootstrap_hides_global_operational_details_but_admin_can_read_them(
    monkeypatch: pytest.MonkeyPatch, multi_user_settings: Settings, two_users, bootstrapped
) -> None:
    import app.main as main_module

    now = datetime.now(UTC)
    task_id = f"shared-task-{uuid4().hex}"
    audit_id = f"shared-audit-{uuid4().hex}"
    with session_scope() as db:
        db.add_all(
            (
                TaskRun(
                    run_id=task_id,
                    task_name="refresh_quotes",
                    status="failed",
                    started_at=now,
                    finished_at=now,
                    result_json={},
                    error="provider detail only for administrators",
                ),
                ProviderAudit(
                    run_id=audit_id,
                    operation="quotes",
                    provider="test-provider",
                    status="failed",
                    latency_ms=1.0,
                    record_count=0,
                    reason="provider detail only for administrators",
                    source_time=now,
                    quality_hash=None,
                ),
            )
        )

    app.dependency_overrides[get_settings] = lambda: multi_user_settings
    monkeypatch.setattr(main_module, "settings", multi_user_settings)
    admin_client = _client_for_user(multi_user_settings, two_users["first_id"])
    member_client = _client_for_user(multi_user_settings, two_users["second_id"])
    try:
        member = member_client.get("/api/bootstrap")
        assert member.status_code == 200, member.text
        assert member.json()["tasks"] == []
        assert member.json()["provider_health"] == []
        assert member.json()["instruments"]
        assert "market_context" in member.json()

        admin = admin_client.get("/api/bootstrap")
        assert admin.status_code == 200, admin.text
        assert any(row["run_id"] == task_id for row in admin.json()["tasks"])
        assert any(row["provider"] == "test-provider" for row in admin.json()["provider_health"])
    finally:
        admin_client.close()
        member_client.close()
        app.dependency_overrides.pop(get_settings, None)


def test_shared_signal_refresh_is_independent_of_every_users_holdings(
    db_session, two_users, bootstrapped
) -> None:
    """Shared snapshots are pure market outputs, not a cross-user portfolio cache."""
    from app.services.holding_service import HoldingService
    from app.services.signal_v05_service import SignalV05Service

    service = SignalV05Service(Settings(_env_file=None, market_provider="mock"))
    service.refresh_all(db_session)
    first = {
        row.instrument_id: (row.score, row.state, row.target_weight, row.first_step_target_weight, row.input_hash, row.evidence_json)
        for row in db_session.scalars(select(SignalSnapshot)).all()
    }
    HoldingService().upsert(
        db_session, user_id=two_users["first_id"], ts_code="510300.SH", shares=10000, cost_price=4.0, target_weight=0.9
    )
    HoldingService().upsert(
        db_session, user_id=two_users["second_id"], ts_code="510300.SH", shares=1, cost_price=99.0, target_weight=0.01
    )
    service.refresh_all(db_session)
    latest: dict[int, SignalSnapshot] = {}
    for row in db_session.scalars(select(SignalSnapshot).order_by(SignalSnapshot.as_of_time)).all():
        latest[row.instrument_id] = row
    assert {
        instrument_id: (row.score, row.state, row.target_weight, row.first_step_target_weight, row.input_hash, row.evidence_json)
        for instrument_id, row in latest.items()
    } == first


def test_owner_migration_declares_per_user_holding_uniqueness_and_backfill() -> None:
    from pathlib import Path

    migration = (
        Path(__file__).parents[1] / "alembic" / "versions" / "1b2c3d4e5f6a_multi_user_portfolio_ownership.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision: str | None = "0a9b1c2d3e4f"' in migration
    assert "holding_import_sessions" in migration
    assert "report_artifacts" in migration
    assert "uq_holdings_user_instrument" in migration
    assert "auth-backfill-legacy-holdings" in (Path(__file__).parents[1] / "app" / "cli.py").read_text(encoding="utf-8")


def test_admin_user_lifecycle_creates_lists_disables_and_resets_password(
    monkeypatch: pytest.MonkeyPatch, multi_user_settings, two_users
) -> None:
    import app.main as main_module

    app.dependency_overrides[get_settings] = lambda: multi_user_settings
    monkeypatch.setattr(main_module, "settings", multi_user_settings)
    admin = _client_for_user(multi_user_settings, two_users["first_id"])
    member = _client_for_user(multi_user_settings, two_users["second_id"])
    csrf = admin.cookies.get("fund-csrf")
    try:
        assert member.get("/api/admin/users").status_code == 403
        assert member.post(
            f"/api/admin/users/{two_users['second_id']}/disable",
            headers={"X-CSRF-Token": member.cookies.get("fund-csrf")},
        ).status_code == 403
        created = admin.post(
            "/api/admin/users",
            json={"username": "managed-member", "email": "managed@example.test", "password": "new password"},
            headers={"X-CSRF-Token": csrf},
        )
        assert created.status_code == 201, created.text
        assert created.json()["role"] == "member"
        assert "password" not in created.text
        user_id = created.json()["id"]
        with session_scope() as db:
            issued_disabled = AuthService().create_session(db, db.get(AuthUser, user_id))

        listed = admin.get("/api/admin/users")
        assert listed.status_code == 200
        assert any(row["username"] == "managed-member" for row in listed.json())

        reset = admin.post(
            f"/api/admin/users/{user_id}/reset-password",
            json={"password": "rotated password"},
            headers={"X-CSRF-Token": csrf},
        )
        assert reset.status_code == 200
        with session_scope() as db:
            user = db.get(AuthUser, user_id)
            assert user is not None and AuthService().verify_password("rotated password", user.password_hash)

        disabled = admin.post(
            f"/api/admin/users/{user_id}/disable", headers={"X-CSRF-Token": csrf}
        )
        assert disabled.status_code == 200
        with session_scope() as db:
            user = db.get(AuthUser, user_id)
            assert user is not None and user.status == "disabled"
            assert AuthService().resolve_session(db, issued_disabled.session_token) is None
            issued = AuthService().create_session(db, db.get(AuthUser, two_users["second_id"]))

        reset_existing = admin.post(
            f"/api/admin/users/{two_users['second_id']}/reset-password",
            json={"password": "member rotated password"},
            headers={"X-CSRF-Token": csrf},
        )
        assert reset_existing.status_code == 200
        with session_scope() as db:
            assert AuthService().resolve_session(db, issued.session_token) is None

        reactivated = admin.post(
            f"/api/admin/users/{user_id}/reactivate", headers={"X-CSRF-Token": csrf}
        )
        assert reactivated.status_code == 200
        assert reactivated.json()["status"] == "active"
        assert admin.get("/api/admin/users", headers={"Authorization": "Bearer legacy-machine-token-only"}).status_code == 401
    finally:
        admin.close()
        member.close()
        app.dependency_overrides.pop(get_settings, None)


def test_admin_can_disable_own_account_when_another_active_admin_remains(
    monkeypatch: pytest.MonkeyPatch, multi_user_settings: Settings, tmp_path
) -> None:
    import app.main as main_module

    app.dependency_overrides[get_settings] = lambda: multi_user_settings
    monkeypatch.setattr(main_module, "settings", multi_user_settings)
    engine = create_engine(f"sqlite:///{(tmp_path / 'self-disable.sqlite3').as_posix()}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    service = AuthService()
    with sessions.begin() as db:
        actor = service.bootstrap_first_admin(db, username="self-disable-admin", password="admin password")
        service.create_user(db, username="second-active-admin", password="second admin password", role="admin")
        issued = service.create_session(db, actor)
        actor_id = actor.id

    def local_db():
        db = sessions()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = local_db
    admin = TestClient(app)
    admin.cookies.set("fund-session", issued.session_token)
    admin.cookies.set("fund-csrf", issued.csrf_token)
    try:
        response = admin.post(
            f"/api/admin/users/{actor_id}/disable",
            headers={"X-CSRF-Token": admin.cookies.get("fund-csrf")},
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "disabled"
        assert admin.get("/api/auth/me").json() == {"authenticated": False, "identifier": None, "role": None}
        with sessions() as db:
            user = db.get(AuthUser, actor_id)
            assert user is not None and user.status == "disabled"
            assert db.scalar(
                select(AuthSession).where(
                    AuthSession.user_id == actor_id, AuthSession.revoked_at.is_not(None)
                )
            ) is not None
    finally:
        admin.close()
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_settings, None)
        engine.dispose()


def test_last_active_admin_cannot_disable_own_account(
    monkeypatch: pytest.MonkeyPatch, multi_user_settings: Settings, tmp_path
) -> None:
    import app.main as main_module

    app.dependency_overrides[get_settings] = lambda: multi_user_settings
    monkeypatch.setattr(main_module, "settings", multi_user_settings)
    engine = create_engine(f"sqlite:///{(tmp_path / 'last-self-disable.sqlite3').as_posix()}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    service = AuthService()
    with sessions.begin() as db:
        actor = service.bootstrap_first_admin(db, username="last-self-disable-admin", password="admin password")
        issued = service.create_session(db, actor)
        actor_id = actor.id

    def local_db():
        db = sessions()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = local_db
    admin = TestClient(app)
    admin.cookies.set("fund-session", issued.session_token)
    admin.cookies.set("fund-csrf", issued.csrf_token)
    try:
        response = admin.post(
            f"/api/admin/users/{actor_id}/disable",
            headers={"X-CSRF-Token": admin.cookies.get("fund-csrf")},
        )
        assert response.status_code == 409
        assert response.json() == {"detail": "the last active admin cannot be disabled"}
        with sessions() as db:
            user = db.get(AuthUser, actor_id)
            assert user is not None and user.status == "active"
    finally:
        admin.close()
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_settings, None)
        engine.dispose()


def test_etf_1430_reports_are_private_and_legacy_bearer_cannot_read_them(
    monkeypatch: pytest.MonkeyPatch, multi_user_settings: Settings, two_users, bootstrapped, tmp_path
) -> None:
    import app.main as main_module

    settings = multi_user_settings.model_copy(update={"reports_dir": tmp_path})
    app.dependency_overrides[get_settings] = lambda: settings
    monkeypatch.setattr(main_module, "settings", settings)
    first = _client_for_user(settings, two_users["first_id"])
    second = _client_for_user(settings, two_users["second_id"])
    try:
        generated = first.post(
            "/api/workbench/1430/generate", headers={"X-CSRF-Token": first.cookies.get("fund-csrf")}
        )
        assert generated.status_code == 200, generated.text
        filename = generated.json()["filename"]
        assert first.get("/api/reports").json()[0]["filename"] == filename
        assert second.get("/api/reports").json() == []
        assert second.get(f"/api/reports/{filename}").status_code == 404
        assert TestClient(app).get(
            "/api/reports", headers={"Authorization": "Bearer legacy-machine-token-only"}
        ).status_code == 401
        assert TestClient(app).get(
            "/api/events", headers={"Authorization": "Bearer legacy-machine-token-only"}
        ).status_code == 401
        with session_scope() as db:
            artifact = next(
                (
                    candidate
                    for candidate in db.scalars(select(ReportArtifact)).all()
                    if Path(candidate.file_path).name == filename
                ),
                None,
            )
            assert artifact is not None and artifact.user_id == two_users["first_id"]
    finally:
        first.close()
        second.close()
        app.dependency_overrides.pop(get_settings, None)


def test_report_generation_uses_system_scope_only_when_auth_is_disabled(
    monkeypatch: pytest.MonkeyPatch, multi_user_settings: Settings, two_users, bootstrapped, tmp_path
) -> None:
    """Offline report generation remains system-scoped; Bearer never authorizes an unsafe user route."""
    import app.main as main_module

    offline = multi_user_settings.model_copy(update={"auth_enabled": False, "reports_dir": tmp_path})
    enabled = multi_user_settings.model_copy(update={"reports_dir": tmp_path})
    app.dependency_overrides[get_settings] = lambda: offline
    monkeypatch.setattr(main_module, "settings", offline)
    try:
        with TestClient(app) as client:
            generated = client.post("/api/reports")
            assert generated.status_code == 200, generated.text
            filename = generated.json()["filename"]
            assert filename in {item["filename"] for item in client.get("/api/reports").json()}

        with session_scope() as db:
            artifact = db.scalar(select(ReportArtifact).where(ReportArtifact.file_path == str(tmp_path / "system" / filename)))
            assert artifact is not None
            assert artifact.user_id is None

        app.dependency_overrides[get_settings] = lambda: enabled
        monkeypatch.setattr(main_module, "settings", enabled)
        with TestClient(app) as anonymous:
            response = anonymous.post(
                "/api/reports", headers={"Authorization": "Bearer legacy-machine-token-only"}
            )
            assert response.status_code == 401
            assert response.json() == {"detail": "database user session required"}
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_member_report_generation_excludes_global_operational_diagnostics(
    db_session, multi_user_settings: Settings, two_users, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Member-owned report payloads and HTML cannot carry global task/provider failures."""
    from app.services.report_service import ReportService

    task_error = "member-report-must-not-see-task-error"
    provider_error = "member-report-must-not-see-provider-error"
    now = datetime.now(UTC)
    db_session.add_all(
        [
            TaskRun(
                run_id=uuid4().hex,
                task_name="private-report-regression",
                status="failed",
                started_at=now,
                finished_at=now,
                result_json={},
                error=task_error,
            ),
            ProviderAudit(
                run_id=uuid4().hex,
                operation="private-report-regression",
                provider="test-provider",
                status="failed",
                latency_ms=1.0,
                record_count=0,
                reason=provider_error,
                source_time=now,
                quality_hash=None,
            ),
        ]
    )
    db_session.flush()

    service = ReportService(multi_user_settings.model_copy(update={"reports_dir": tmp_path}))
    captured_payloads: dict[str, dict] = {}
    original_bootstrap = service.dashboard.bootstrap

    def capture_bootstrap(db, *, user_id=None, include_operational_details=True):
        payload = original_bootstrap(
            db, user_id=user_id, include_operational_details=include_operational_details
        )
        captured_payloads["system" if user_id is None else str(user_id)] = payload
        return payload

    monkeypatch.setattr(service.dashboard, "bootstrap", capture_bootstrap)
    system_report = service.generate(db_session)
    admin_report = service.generate(db_session, user_id=two_users["first_id"])
    member_report = service.generate(db_session, user_id=two_users["second_id"])

    member_payload = captured_payloads[str(two_users["second_id"])]
    assert member_payload["tasks"] == []
    assert member_payload["provider_health"] == []
    member_html = Path(member_report["path"]).read_text(encoding="utf-8")
    assert task_error not in member_html
    assert provider_error not in member_html

    for owner_key, report in (("system", system_report), (str(two_users["first_id"]), admin_report)):
        payload = captured_payloads[owner_key]
        assert task_error in [item["error"] for item in payload["tasks"]]
        assert provider_error in [item["reason"] for item in payload["provider_health"]]
        html = Path(report["path"]).read_text(encoding="utf-8")
        assert task_error not in html
        assert provider_error not in html


def test_report_download_uses_exact_registered_owner_artifact_without_path_leakage(
    monkeypatch: pytest.MonkeyPatch, multi_user_settings: Settings, two_users, bootstrapped, tmp_path
) -> None:
    """Filename wildcards cannot select a near match, outside artifact, or another owner's report."""
    import app.main as main_module

    settings = multi_user_settings.model_copy(update={"reports_dir": tmp_path})
    exact_name = "owner_report_%_2026.json"
    near_name = "owner_report_A_2026.json"
    unmatched_name = "missing_report_%_2026.json"
    unmatched_near_name = "missing_report_A_2026.json"
    foreign_name = "foreign_report_%_2026.json"
    exact_path = tmp_path / "user-one" / exact_name
    near_path = tmp_path / "sibling-artifacts" / near_name
    unmatched_near_path = tmp_path / "sibling-artifacts" / unmatched_near_name
    foreign_path = tmp_path / "user-two" / foreign_name
    for path, content in (
        (exact_path, '{"source":"exact"}'),
        (near_path, '{"source":"near"}'),
        (unmatched_near_path, '{"source":"unmatched-near"}'),
        (foreign_path, '{"source":"foreign"}'),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    now = datetime.now(UTC)
    with session_scope() as db:
        db.add_all(
            [
                ReportArtifact(
                    user_id=two_users["first_id"],
                    report_type="near",
                    as_of_time=now,
                    file_path=str(near_path),
                    content_hash="a" * 64,
                    metadata_json={"filename": near_name},
                ),
                ReportArtifact(
                    user_id=two_users["first_id"],
                    report_type="exact",
                    as_of_time=now,
                    file_path=str(exact_path),
                    content_hash="b" * 64,
                    metadata_json={"filename": exact_name},
                ),
                ReportArtifact(
                    user_id=two_users["first_id"],
                    report_type="unmatched-near",
                    as_of_time=now,
                    file_path=str(unmatched_near_path),
                    content_hash="c" * 64,
                    metadata_json={"filename": unmatched_near_name},
                ),
                ReportArtifact(
                    user_id=two_users["second_id"],
                    report_type="foreign",
                    as_of_time=now,
                    file_path=str(foreign_path),
                    content_hash="d" * 64,
                    metadata_json={"filename": foreign_name},
                ),
            ]
        )

    app.dependency_overrides[get_settings] = lambda: settings
    monkeypatch.setattr(main_module, "settings", settings)
    first = _client_for_user(settings, two_users["first_id"])
    try:
        exact = first.get(f"/api/reports/{quote(exact_name, safe='')}")
        assert exact.status_code == 200, exact.text
        assert exact.json() == {"source": "exact"}

        unmatched = first.get(f"/api/reports/{quote(unmatched_name, safe='')}")
        assert unmatched.status_code == 404
        assert str(tmp_path) not in unmatched.text

        foreign = first.get(f"/api/reports/{quote(foreign_name, safe='')}")
        assert foreign.status_code == 404
        assert str(tmp_path) not in foreign.text
    finally:
        first.close()
        app.dependency_overrides.pop(get_settings, None)


def test_system_report_listing_skips_stale_files_without_consuming_limit(
    multi_user_settings: Settings, tmp_path
) -> None:
    settings = multi_user_settings.model_copy(update={"auth_enabled": False, "reports_dir": tmp_path})
    stale_dir = tmp_path / "deleted-reports"
    stale_dir.mkdir()
    stale_path = stale_dir / "stale-system.json"
    stale_path.write_text("stale", encoding="utf-8")
    stale_path.unlink()
    stale_dir.rmdir()

    valid_dir = tmp_path / "current-reports"
    valid_dir.mkdir()
    unsupported_path = valid_dir / "unsupported-system.txt"
    unsupported_path.write_text("unsupported", encoding="utf-8")
    valid_path = valid_dir / "valid-system.json"
    valid_path.write_text("{\"status\": \"ok\"}", encoding="utf-8")
    now = datetime.now(UTC)
    with session_scope() as db:
        db.add_all(
            [
                ReportArtifact(
                    report_type="system-unsupported",
                    as_of_time=now,
                    created_at=now + timedelta(seconds=2),
                    file_path=str(unsupported_path),
                    content_hash="e" * 64,
                    metadata_json={"scope": "system", "filename": unsupported_path.name},
                ),
                ReportArtifact(
                    report_type="system-stale",
                    as_of_time=now,
                    created_at=now + timedelta(seconds=1),
                    file_path=str(stale_path),
                    content_hash="c" * 64,
                    metadata_json={"scope": "system", "filename": stale_path.name},
                ),
                ReportArtifact(
                    report_type="system-valid",
                    as_of_time=now,
                    created_at=now,
                    file_path=str(valid_path),
                    content_hash="d" * 64,
                    metadata_json={"scope": "system", "filename": valid_path.name},
                ),
            ]
        )

    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.get("/api/reports?limit=1")
            assert response.status_code == 200, response.text
            listed = response.json()
            assert len(listed) == 1
            assert listed[0]["filename"] == valid_path.name
            assert listed[0]["url"] == f"/api/reports/{valid_path.name}"
            assert unsupported_path.name not in response.text
            assert stale_path.name not in response.text
            assert str(tmp_path) not in response.text
            downloaded = client.get(listed[0]["url"])
            assert downloaded.status_code == 200
            assert downloaded.json() == {"status": "ok"}
    finally:
        app.dependency_overrides.pop(get_settings, None)

    with session_scope() as db:
        stored = db.scalars(
            select(ReportArtifact).where(
                ReportArtifact.file_path.in_([str(unsupported_path), str(stale_path), str(valid_path)])
            )
        ).all()
        assert {row.file_path for row in stored} == {
            str(unsupported_path),
            str(stale_path),
            str(valid_path),
        }


def test_cli_holding_commands_preserve_offline_legacy_scope_and_require_active_owner_when_enabled(
    monkeypatch: pytest.MonkeyPatch, multi_user_settings: Settings, two_users, bootstrapped
) -> None:
    """Offline CLI holdings remain system scoped; enabled CLI never selects an ambient owner."""
    from app import cli

    runner = CliRunner()
    offline = multi_user_settings.model_copy(update={"auth_enabled": False})
    monkeypatch.setattr(cli, "get_settings", lambda: offline)

    offline_set = runner.invoke(
        cli.app,
        ["holding-set", "510300.SH", "--shares", "11", "--cost-price", "4.1", "--notes", "offline-cli"],
    )
    assert offline_set.exit_code == 0, offline_set.output
    with session_scope() as db:
        legacy = db.scalar(select(Holding).where(Holding.notes == "offline-cli"))
        assert legacy is not None
        assert legacy.user_id is None

    offline_delete = runner.invoke(cli.app, ["holding-delete", "510300.SH"])
    assert offline_delete.exit_code == 0, offline_delete.output
    with session_scope() as db:
        assert db.scalar(select(Holding).where(Holding.notes == "offline-cli")) is None

    monkeypatch.setattr(cli, "get_settings", lambda: multi_user_settings)
    missing_owner = runner.invoke(cli.app, ["holding-set", "510300.SH", "--shares", "12", "--cost-price", "4.2"])
    assert missing_owner.exit_code != 0

    owner_set = runner.invoke(
        cli.app,
        [
            "holding-set",
            "510300.SH",
            "--username",
            two_users["first_username"],
            "--shares",
            "12",
            "--cost-price",
            "4.2",
            "--notes",
            "enabled-cli",
        ],
    )
    assert owner_set.exit_code == 0, owner_set.output
    with session_scope() as db:
        owned = db.scalar(select(Holding).where(Holding.notes == "enabled-cli"))
        assert owned is not None
        assert owned.user_id == two_users["first_id"]

    missing_owner_delete = runner.invoke(cli.app, ["holding-delete", "510300.SH"])
    assert missing_owner_delete.exit_code == 1
    assert missing_owner_delete.output == "holding owner rejected\n"
    foreign_delete = runner.invoke(
        cli.app,
        ["holding-delete", "510300.SH", "--username", two_users["second_username"]],
    )
    assert foreign_delete.exit_code == 0, foreign_delete.output
    assert foreign_delete.output == "not found\n"
    with session_scope() as db:
        assert db.scalar(select(Holding).where(Holding.notes == "enabled-cli")) is not None

    owner_delete = runner.invoke(
        cli.app,
        ["holding-delete", "510300.SH", "--username", two_users["first_username"]],
    )
    assert owner_delete.exit_code == 0, owner_delete.output
    assert owner_delete.output == "deleted\n"
    with session_scope() as db:
        assert db.scalar(select(Holding).where(Holding.notes == "enabled-cli")) is None
        AuthService().disable_user(db, two_users["second_id"])

    disabled_owner = runner.invoke(
        cli.app,
        [
            "holding-set",
            "510300.SH",
            "--username",
            two_users["second_username"],
            "--shares",
            "13",
            "--cost-price",
            "4.3",
        ],
    )
    assert disabled_owner.exit_code == 1
    assert disabled_owner.output == "holding owner rejected\n"


def test_report_listing_rejects_external_owned_artifacts_and_preserves_owner_boundary(
    monkeypatch: pytest.MonkeyPatch, multi_user_settings: Settings, two_users, tmp_path
) -> None:
    """Listing has the same root containment and ownership behavior as report download."""
    import app.main as main_module

    reports_root = tmp_path / "reports"
    reports_root.mkdir()
    first_dir = reports_root / f"user-{two_users['first_id']}"
    second_dir = reports_root / f"user-{two_users['second_id']}"
    first_dir.mkdir()
    second_dir.mkdir()
    valid_path = first_dir / "in-root-owned.json"
    valid_path.write_text('{"owner": "first"}', encoding="utf-8")
    external_path = tmp_path / "outside-owned.json"
    external_path.write_text('{"owner": "first"}', encoding="utf-8")
    foreign_path = second_dir / "foreign-owned.json"
    foreign_path.write_text('{"owner": "second"}', encoding="utf-8")
    settings = multi_user_settings.model_copy(update={"reports_dir": reports_root})
    now = datetime.now(UTC)
    with session_scope() as db:
        db.add_all(
            [
                ReportArtifact(
                    user_id=two_users["first_id"],
                    report_type="in-root",
                    as_of_time=now,
                    file_path=str(valid_path),
                    content_hash="a" * 64,
                    metadata_json={"scope": "private", "filename": valid_path.name},
                ),
                ReportArtifact(
                    user_id=two_users["first_id"],
                    report_type="external",
                    as_of_time=now + timedelta(seconds=1),
                    file_path=str(external_path),
                    content_hash="b" * 64,
                    metadata_json={"scope": "private", "filename": external_path.name},
                ),
                ReportArtifact(
                    user_id=two_users["second_id"],
                    report_type="foreign",
                    as_of_time=now + timedelta(seconds=2),
                    file_path=str(foreign_path),
                    content_hash="c" * 64,
                    metadata_json={"scope": "private", "filename": foreign_path.name},
                ),
            ]
        )

    app.dependency_overrides[get_settings] = lambda: settings
    monkeypatch.setattr(main_module, "settings", settings)
    first = _client_for_user(settings, two_users["first_id"])
    second = _client_for_user(settings, two_users["second_id"])
    try:
        first_list = first.get("/api/reports")
        assert first_list.status_code == 200, first_list.text
        assert [item["filename"] for item in first_list.json()] == [valid_path.name]
        assert external_path.name not in first_list.text
        assert str(external_path) not in first_list.text
        assert foreign_path.name not in first_list.text

        second_list = second.get("/api/reports")
        assert second_list.status_code == 200, second_list.text
        assert [item["filename"] for item in second_list.json()] == [foreign_path.name]
        assert valid_path.name not in second_list.text
    finally:
        first.close()
        second.close()
        app.dependency_overrides.pop(get_settings, None)


def test_sse_event_visibility_allows_global_and_matching_owner_only() -> None:
    from app.api.router import _event_is_visible_to_user

    global_event = EventLog(event_type="market_context.updated", payload_json={"status": "ok"})
    own_event = EventLog(event_type="report.generated", payload_json={"user_id": 7})
    other_event = EventLog(event_type="report.generated", payload_json={"user_id": 8})
    malformed_private = EventLog(event_type="holdings.updated", payload_json={})
    assert _event_is_visible_to_user(global_event, 7)
    assert _event_is_visible_to_user(own_event, 7)
    assert not _event_is_visible_to_user(other_event, 7)
    assert not _event_is_visible_to_user(malformed_private, 7)


def test_holding_mutation_event_is_visible_only_to_its_owner(
    monkeypatch: pytest.MonkeyPatch, multi_user_settings: Settings, two_users, bootstrapped
) -> None:
    """The API mutation persists an owner-bound SSE payload, never an ambient owner."""
    import app.main as main_module
    from app.api.router import _event_is_visible_to_user

    app.dependency_overrides[get_settings] = lambda: multi_user_settings
    monkeypatch.setattr(main_module, "settings", multi_user_settings)
    owner = _client_for_user(multi_user_settings, two_users["first_id"])
    try:
        response = owner.put(
            "/api/holdings/510300.SH",
            json={"ts_code": "510300.SH", "shares": 12, "cost_price": 4.1},
            headers={"X-CSRF-Token": owner.cookies.get("fund-csrf")},
        )
        assert response.status_code == 200, response.text
        with session_scope() as db:
            event = db.scalar(select(EventLog).where(EventLog.event_type == "holdings.updated").order_by(EventLog.id.desc()))
            assert event is not None
            assert event.payload_json == {
                "ts_code": "510300.SH",
                "action": "upsert",
                "user_id": two_users["first_id"],
            }
            assert _event_is_visible_to_user(event, two_users["first_id"])
            assert not _event_is_visible_to_user(event, two_users["second_id"])
    finally:
        owner.close()
        app.dependency_overrides.pop(get_settings, None)


def test_instrument_holding_overlay_is_scoped_to_current_user(
    monkeypatch: pytest.MonkeyPatch, multi_user_settings: Settings, two_users, bootstrapped
) -> None:
    import app.main as main_module

    app.dependency_overrides[get_settings] = lambda: multi_user_settings
    monkeypatch.setattr(main_module, "settings", multi_user_settings)
    first = _client_for_user(multi_user_settings, two_users["first_id"])
    second = _client_for_user(multi_user_settings, two_users["second_id"])
    try:
        assert first.put(
            "/api/holdings/510300.SH",
            json={"ts_code": "510300.SH", "shares": 12, "cost_price": 4.1},
            headers={"X-CSRF-Token": first.cookies.get("fund-csrf")},
        ).status_code == 200
        first_row = next(row for row in first.get("/api/instruments").json() if row["ts_code"] == "510300.SH")
        second_row = next(row for row in second.get("/api/instruments").json() if row["ts_code"] == "510300.SH")
        assert first_row["holding"] == {"shares": 12.0, "cost_price": 4.1, "target_weight": None, "notes": None}
        assert second_row["holding"] is None
    finally:
        first.close()
        second.close()
        app.dependency_overrides.pop(get_settings, None)


def test_legacy_backfill_only_assigns_explicitly_private_reports(two_users, bootstrapped) -> None:
    """Unknown NULL-owner reports stay system-only; retrying the audited command is idempotent."""
    from app.cli import app as cli_app

    with session_scope() as db:
        instrument = db.scalar(select(Instrument).where(Instrument.ts_code == "510300.SH"))
        assert instrument is not None
        db.add(Holding(instrument_id=instrument.id, shares=1, cost_price=1, notes="legacy-backfill-test"))
        db.add(
            HoldingImportSession(
                session_id="d" * 32,
                status="ready",
                image_sha256="c" * 64,
                detected_mime="image/png",
                image_bytes=1,
                image_width=1,
                image_height=1,
                ocr_mode="disabled",
                ocr_backend="test",
                ocr_model="test",
                ocr_version="test",
                candidate_count=0,
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )
        )
        db.add_all(
            [
                ReportArtifact(report_type="legacy-system", as_of_time=datetime.now(UTC), file_path="system.json", content_hash="a" * 64),
                ReportArtifact(
                    report_type="legacy-private",
                    as_of_time=datetime.now(UTC),
                    file_path="private.json",
                    content_hash="b" * 64,
                    metadata_json={"scope": "private"},
                ),
            ]
        )
    with session_scope() as db:
        before = {
            "holdings": int(db.scalar(select(func.count()).select_from(Holding).where(Holding.user_id.is_(None))) or 0),
            "holding_import_sessions": int(
                db.scalar(select(func.count()).select_from(HoldingImportSession).where(HoldingImportSession.user_id.is_(None)))
                or 0
            ),
            "private_report_artifacts": int(
                db.scalar(
                    select(func.count()).select_from(ReportArtifact).where(
                        ReportArtifact.user_id.is_(None),
                        ReportArtifact.metadata_json["scope"].as_string() == "private",
                    )
                )
                or 0
            ),
        }
    runner = CliRunner()
    result = runner.invoke(cli_app, ["auth-backfill-legacy-holdings", "--username", two_users["first_username"], "--apply"])
    assert result.exit_code == 0, result.output
    assert two_users["first_username"] not in result.output
    assert json.loads(result.output) == before
    retry = runner.invoke(cli_app, ["auth-backfill-legacy-holdings", "--username", two_users["first_username"], "--apply"])
    assert retry.exit_code == 0, retry.output
    assert retry.output.strip() == '{"holdings": 0, "holding_import_sessions": 0, "private_report_artifacts": 0}'
    with session_scope() as db:
        assert db.scalar(select(func.count()).select_from(Holding).where(Holding.user_id.is_(None))) == 0
        assert db.scalar(select(func.count()).select_from(HoldingImportSession).where(HoldingImportSession.user_id.is_(None))) == 0
        assert db.scalar(
            select(func.count()).select_from(ReportArtifact).where(
                ReportArtifact.user_id.is_(None),
                ReportArtifact.metadata_json["scope"].as_string() == "private",
            )
        ) == 0
        assert db.scalar(select(Holding.user_id).where(Holding.notes == "legacy-backfill-test")) == two_users["first_id"]
        assert db.scalar(select(HoldingImportSession.user_id).where(HoldingImportSession.session_id == "d" * 32)) == two_users["first_id"]
        assert db.scalar(select(ReportArtifact.user_id).where(ReportArtifact.file_path == "private.json")) == two_users["first_id"]
        assert db.scalar(select(ReportArtifact.user_id).where(ReportArtifact.file_path == "system.json")) is None
