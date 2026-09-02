from __future__ import annotations

import secrets

import pytest
from app.api.schemas import ReviewEnqueueRequest, ReviewMemo, ReviewTransitionRequest, TaskRequest
from app.core.config import Settings
from app.models import EventLog, Holding, RuntimeSetting, SignalSnapshot, TaskRun
from app.services.task_service import TaskExecutionError, TaskService
from fastapi.testclient import TestClient
from sqlalchemy import select, text


@pytest.fixture(scope="module", autouse=True)
def review_storage_triggers(database):
    """Install migration-owned triggers for real Review API tests only."""
    from app.db.session import get_engine

    with get_engine().begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TRIGGER IF NOT EXISTS trg_analysis_runs_append_only
            BEFORE UPDATE ON analysis_runs
            BEGIN SELECT RAISE(ABORT, 'analysis_runs are append-only'); END
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TRIGGER IF NOT EXISTS trg_analysis_runs_no_delete
            BEFORE DELETE ON analysis_runs
            BEGIN SELECT RAISE(ABORT, 'analysis_runs are append-only'); END
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TRIGGER IF NOT EXISTS trg_agent_review_candidates_immutable
            BEFORE UPDATE ON agent_review_candidates
            WHEN NEW.candidate_id IS NOT OLD.candidate_id
              OR NEW.runner IS NOT OLD.runner
              OR NEW.bundle_hash IS NOT OLD.bundle_hash
              OR NEW.memo_hash IS NOT OLD.memo_hash
              OR NEW.memo_json IS NOT OLD.memo_json
              OR NEW.created_at IS NOT OLD.created_at
            BEGIN SELECT RAISE(ABORT, 'review candidate identity and evidence are immutable'); END
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TRIGGER IF NOT EXISTS trg_agent_review_candidates_no_delete
            BEFORE DELETE ON agent_review_candidates
            BEGIN SELECT RAISE(ABORT, 'review candidates are append-only'); END
            """
        )
    yield


def test_review_api_schemas_are_strict_and_bounded() -> None:
    request = ReviewEnqueueRequest(
        runner="codex_review_runner",
        bundle_hash="a" * 64,
        memo=ReviewMemo(summary="validated", evidence_ids=[], risk_flags=[], limitations=[]),
    )
    assert request.bundle_hash == "a" * 64
    assert TaskRequest(limit=0, force=False).compact() == {"limit": 0, "force": False}
    assert ReviewTransitionRequest(note="n" * 2000).note == "n" * 2000


def test_review_api_schemas_reject_extra_fields() -> None:
    try:
        ReviewEnqueueRequest(
            runner="codex_review_runner",
            bundle_hash="a" * 64,
            memo={"summary": "ok", "unexpected": "blocked"},
        )
    except Exception:
        pass
    else:
        raise AssertionError("review memo must reject unknown fields")


def test_task_request_normalizes_bounded_codes() -> None:
    request = TaskRequest(codes=(" 510300.sh ", "159915"))

    assert request.codes == ["510300.SH", "159915"]


@pytest.mark.parametrize(
    "codes",
    [
        ["A"] * 201,
        ["A" * 33],
        ["bad/code"],
        [""],
    ],
)
def test_task_request_rejects_oversized_or_unsafe_codes(codes: list[str]) -> None:
    with pytest.raises(ValueError):
        TaskRequest(codes=codes)


def test_task_failure_recovers_after_real_sqlite_integrity_error(db_session) -> None:
    service = TaskService(Settings(_env_file=None, market_provider="mock", analysis_enabled=False))

    def fail_inside_transaction(db, task_name, run_id, **kwargs):
        del task_name, kwargs
        db.execute(
            text(
                "INSERT INTO task_runs "
                "(run_id, task_name, status, started_at, result_json) "
                "VALUES (:run_id, 'test', 'running', CURRENT_TIMESTAMP, '{}')"
            ),
            {"run_id": run_id},
        )
        return {}

    service._execute = fail_inside_transaction
    run_id = "real-integrity-failure"

    with pytest.raises(TaskExecutionError) as raised:
        service.run(db_session, "generate_report", run_id=run_id)

    assert raised.value.run_id == run_id
    assert raised.value.failure_class == "sqlalchemy.exc.IntegrityError"
    assert str(raised.value) == f"task failed: {run_id} ({raised.value.failure_class})"
    task = db_session.scalar(select(TaskRun).where(TaskRun.run_id == run_id))
    assert task is not None
    assert task.status == "failed"
    assert task.error == raised.value.failure_class
    assert task.result_json == {"status": "failed", "failure_class": raised.value.failure_class}
    event = db_session.scalar(
        select(EventLog)
        .where(EventLog.event_type == "task.updated")
        .order_by(EventLog.id.desc())
    )
    assert event is not None
    assert event.payload_json == {
        "run_id": run_id,
        "task_name": "generate_report",
        "status": "failed",
        "failure_class": raised.value.failure_class,
    }
    # The caller's Session must be usable after TaskService returns.
    assert db_session.scalar(select(TaskRun.run_id).where(TaskRun.run_id == run_id)) == run_id


def test_task_failure_audit_sanitizes_non_db_exception(db_session) -> None:
    service = TaskService(Settings(_env_file=None, market_provider="mock", analysis_enabled=False))

    def fail_inside_task(db, task_name, run_id, **kwargs):
        del db, task_name, run_id, kwargs
        raise RuntimeError("secret-url=https://private.invalid/token?key=secret")

    service._execute = fail_inside_task
    run_id = "non-db-failure"
    with pytest.raises(TaskExecutionError) as raised:
        service.run(db_session, "generate_report", run_id=run_id)

    assert raised.value.run_id == run_id
    assert raised.value.failure_class == "builtins.RuntimeError"
    task = db_session.scalar(select(TaskRun).where(TaskRun.run_id == run_id))
    assert task is not None
    assert task.error == "builtins.RuntimeError"
    assert "private.invalid" not in repr(task.result_json)
    assert "private.invalid" not in repr(task.error)


def test_task_api_maps_execution_error_to_safe_run_and_failure_class(monkeypatch, database) -> None:
    from app.main import app

    def fail(*args, **kwargs):
        del args, kwargs
        raise TaskExecutionError("api-safe-run", "builtins.RuntimeError")

    monkeypatch.setattr(TaskService, "run", fail)
    with TestClient(app) as client:
        response = client.post("/api/tasks/generate_report", json={})
    assert response.status_code == 500
    assert response.json() == {
        "detail": {"run_id": "api-safe-run", "failure_class": "builtins.RuntimeError"}
    }
    assert "traceback" not in response.text.lower()
    assert "secret" not in response.text.lower()


def test_review_api_real_state_machine_is_hash_bound_and_does_not_touch_domain(monkeypatch, bootstrapped) -> None:
    from app.db.session import SessionLocal
    from app.main import app

    def fail_if_called(*args, **kwargs):
        raise AssertionError(f"review API invoked subprocess: {args!r} {kwargs!r}")

    monkeypatch.setattr("subprocess.run", fail_if_called)
    with SessionLocal() as db:
        before = {
            "holdings": db.query(Holding).count(),
            "signals": db.query(SignalSnapshot).count(),
            "settings": db.query(RuntimeSetting).count(),
        }

    payload = {
        "runner": "codex_review_runner",
        "bundle_hash": "a" * 64,
        "memo": {
            "summary": "validated candidate",
            "evidence_ids": ["news:1"],
            "risk_flags": [],
            "limitations": [],
        },
    }
    approved_fields = {
        "candidate_id",
        "runner",
        "bundle_hash",
        "memo_hash",
        "memo",
        "review_status",
        "created_at",
        "updated_at",
        "accepted_at",
        "rejected_at",
        "review_note",
    }
    with TestClient(app) as client:
        created = client.post("/api/analysis/reviews", json=payload)
        assert created.status_code == 201
        candidate_id = created.json()["candidate_id"]
        assert set(created.json()) == approved_fields
        listed = client.get("/api/analysis/reviews")
        assert listed.status_code == 200
        assert any(item["candidate_id"] == candidate_id for item in listed.json())
        detail = client.get(f"/api/analysis/reviews/{candidate_id}")
        assert detail.status_code == 200
        accepted = client.post(
            f"/api/analysis/reviews/{candidate_id}/accept", json={"note": "approved"}
        )
        assert accepted.status_code == 200
        assert accepted.json()["review_status"] == "accepted"
        repeated = client.post(
            f"/api/analysis/reviews/{candidate_id}/accept", json={"note": "ignored"}
        )
        assert repeated.status_code == 200
        assert repeated.json()["review_status"] == "accepted"
        assert repeated.json()["review_note"] == "approved"
        opposite = client.post(f"/api/analysis/reviews/{candidate_id}/reject", json={})
        assert opposite.status_code == 409
        unknown = client.get("/api/analysis/reviews/missing-review-candidate")
        assert unknown.status_code == 404
        for invalid in (
            {**payload, "bundle_hash": "invalid"},
            {**payload, "memo": {**payload["memo"], "unexpected": "blocked"}},
            {**payload, "memo": {**payload["memo"], "summary": "https://private.invalid"}},
            {**payload, "raw_bundle": {"secret": "must not cross API"}},
        ):
            assert client.post("/api/analysis/reviews", json=invalid).status_code == 422

    with SessionLocal() as db:
        after = {
            "holdings": db.query(Holding).count(),
            "signals": db.query(SignalSnapshot).count(),
            "settings": db.query(RuntimeSetting).count(),
        }
    assert after == before


def test_review_api_auth_boundary_and_storage_readiness(monkeypatch, database) -> None:
    from app.core.security import csrf_cookie_name, session_cookie_name
    from app.db.session import get_engine, session_scope
    from app.main import app, settings
    from app.services.auth_service import AuthService

    old_auth, old_token = settings.auth_enabled, settings.private_access_token
    settings.auth_enabled = True
    settings.private_access_token = "synthetic-test-token"
    payload = {
        "runner": "codex_review_runner",
        "bundle_hash": "b" * 64,
        "memo": {"summary": "auth boundary", "evidence_ids": [], "risk_flags": [], "limitations": []},
    }
    try:
        with session_scope() as db:
            admin = AuthService().create_user(
                db,
                username=f"analysis-admin-{secrets.token_hex(6)}",
                password="test-only-admin-password",
                role="admin",
            )
            issued = AuthService().create_session(db, admin)
        with TestClient(app) as client:
            assert client.post("/api/analysis/reviews", json=payload).status_code == 401
            legacy_bearer = client.post(
                "/api/analysis/reviews",
                json=payload,
                headers={"Authorization": "Bearer synthetic-test-token"},
            )
            assert legacy_bearer.status_code == 401
            client.cookies.set(session_cookie_name(settings), issued.session_token)
            client.cookies.set(csrf_cookie_name(settings), issued.csrf_token)
            csrf_headers = {"X-CSRF-Token": issued.csrf_token}
            authorized = client.post("/api/analysis/reviews", json=payload, headers=csrf_headers)
            assert authorized.status_code == 201, authorized.text

            with get_engine().begin() as connection:
                connection.exec_driver_sql("DROP TRIGGER trg_agent_review_candidates_no_delete")
            try:
                unavailable = client.get("/api/analysis/reviews")
                assert unavailable.status_code == 503
            finally:
                with get_engine().begin() as connection:
                    connection.exec_driver_sql(
                        """
                        CREATE TRIGGER trg_agent_review_candidates_no_delete
                        BEFORE DELETE ON agent_review_candidates
                        BEGIN SELECT RAISE(ABORT, 'review candidates are append-only'); END
                        """
                    )
    finally:
        settings.auth_enabled, settings.private_access_token = old_auth, old_token
