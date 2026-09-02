from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Lock, Thread

import pytest
from app.db.base import Base
from app.models import AuthSession, AuthUser, EventLog
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from typer.testing import CliRunner


def test_auth_user_normalizes_identifiers_and_enforces_unique_username(db_session) -> None:
    from app.services.auth_service import AuthService

    first = AuthUser(
        username="  Jovi ",
        email="  JOVI@Example.Test ",
        password_hash=AuthService().hash_password("correct horse battery staple"),
        role="admin",
        status="active",
    )
    db_session.add(first)
    db_session.flush()

    assert first.username == "jovi"
    assert first.email == "jovi@example.test"

    duplicate = AuthUser(
        username="JOVI",
        password_hash=AuthService().hash_password("correct horse battery staple"),
        role="member",
        status="active",
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_auth_user_structurally_validates_password_hash_without_argon2_computation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import argon2
    from app.services.auth_service import AuthService

    password_hash = AuthService().hash_password("correct horse battery staple")
    monkeypatch.setattr(
        argon2.PasswordHasher,
        "verify",
        lambda *_: pytest.fail("model validation must not run Argon2 verification"),
    )

    user = AuthUser(
        username="structural-hash",
        password_hash=password_hash,
        role="member",
        status="active",
    )

    assert user.password_hash == password_hash


@pytest.mark.parametrize(
    "password_hash",
    [
        "plaintext-password",
        "$argon2id$placeholder",
        "$argon2id$v=19$m=65536,t=3,p=4$%%%$YWJj",
        "$argon2id$v=19$m=65536,t=3,p=4$$YWJj",
        "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$",
        "$argon2id$v=19$m=not-a-number,t=3,p=4$c2FsdA$YWJj",
    ],
)
def test_auth_user_rejects_non_parseable_argon2id_hashes(password_hash: str, db_session) -> None:
    from app.services.auth_service import AuthService

    with pytest.raises(ValueError, match="Argon2id"):
        AuthUser(
            username="invalid-password-hash",
            password_hash=password_hash,
            role="member",
            status="active",
        )
    assert not AuthService().verify_password("any password", password_hash)
    assert db_session.scalar(
        select(func.count()).select_from(AuthUser).where(AuthUser.username == "invalid-password-hash")
    ) == 0


def test_auth_service_hashes_password_and_persists_only_session_hash(db_session) -> None:
    from app.services.auth_service import AuthService

    service = AuthService()
    user = service.create_user(
        db_session,
        username="Jovi",
        email="jovi@example.test",
        password="correct horse battery staple",
        role="admin",
    )
    issued = service.create_session(db_session, user)
    db_session.flush()

    stored = db_session.get(AuthSession, issued.session_id)
    assert user.password_hash.startswith("$argon2id$")
    assert service.verify_password("correct horse battery staple", user.password_hash)
    assert not service.verify_password("wrong password", user.password_hash)
    assert stored is not None
    assert stored.session_hash != issued.session_token
    assert stored.csrf_hash != issued.csrf_token
    assert len(stored.session_hash) == len(stored.csrf_hash) == 64
    assert service.resolve_session(db_session, issued.session_token) == user


def test_auth_service_rejects_expired_or_revoked_sessions(db_session) -> None:
    from app.services.auth_service import AuthService

    service = AuthService()
    user = service.create_user(db_session, username="member-expiry", password="correct horse battery staple")
    expired = service.create_session(
        db_session,
        user,
        now=datetime(2026, 9, 1, tzinfo=UTC),
        ttl=timedelta(minutes=1),
    )
    active = service.create_session(db_session, user)
    db_session.flush()

    assert service.resolve_session(db_session, expired.session_token, now=datetime(2026, 9, 1, 0, 2, tzinfo=UTC)) is None
    assert service.revoke_session(db_session, active.session_token)
    assert service.resolve_session(db_session, active.session_token) is None


def test_auth_service_revokes_all_sessions_and_does_not_serialize_secrets(db_session) -> None:
    from app.services.auth_service import AuthService

    service = AuthService()
    user = service.create_user(db_session, username="member-revoke", password="correct horse battery staple")
    first = service.create_session(db_session, user)
    second = service.create_session(db_session, user)
    db_session.flush()

    assert service.revoke_user_sessions(db_session, user.id) == 2
    assert service.resolve_session(db_session, first.session_token) is None
    assert service.resolve_session(db_session, second.session_token) is None
    assert "session_token" not in repr(first)
    assert "csrf_token" not in repr(first)


def test_event_stream_stops_after_its_original_session_is_revoked(db_session) -> None:
    """A long-lived stream must not outlive the opaque DB session that opened it."""

    from app.api.router import _event_stream
    from app.services.auth_service import AuthService

    service = AuthService()
    user = service.create_user(db_session, username="stream-member", password="correct horse battery staple")
    issued = service.create_session(db_session, user)
    db_session.commit()
    after_id = int(db_session.scalar(select(func.max(EventLog.id))) or 0)

    async def assert_stream_closes() -> None:
        stream = _event_stream(
            auth_enabled=True,
            session_token=issued.session_token,
            user_id=user.id,
            after_id=after_id,
            poll_interval_seconds=0,
        )
        assert await anext(stream) == "retry: 3000\n\n"
        assert await anext(stream) == ": keepalive\n\n"

        service.revoke_session(db_session, issued.session_token)
        db_session.commit()

        with pytest.raises(StopAsyncIteration):
            await anext(stream)

    asyncio.run(assert_stream_closes())


def test_last_admin_disable_is_serialized_across_sqlite_sessions(tmp_path) -> None:
    """Two competing disable requests may not commit a zero-active-admin state."""

    from app.services.auth_service import AuthService, LastActiveAdminError

    engine = create_engine(
        f"sqlite:///{(tmp_path / 'last-admin-race.sqlite3').as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    service = AuthService()
    with sessions.begin() as db:
        first = service.bootstrap_first_admin(db, username="race-admin-a", password="correct horse battery staple")
        second = service.create_user(db, username="race-admin-b", password="correct horse battery staple", role="admin")
        target_ids = (first.id, second.id)

    barrier = Barrier(2)
    result_lock = Lock()
    outcomes: list[str] = []

    def disable(user_id: int) -> None:
        try:
            with sessions.begin() as db:
                barrier.wait(timeout=5)
                service.disable_user(db, user_id)
            outcome = "disabled"
        except LastActiveAdminError:
            outcome = "last_admin"
        with result_lock:
            outcomes.append(outcome)

    workers = [Thread(target=disable, args=(user_id,)) for user_id in target_ids]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=15)

    assert all(not worker.is_alive() for worker in workers)
    assert sorted(outcomes) == ["disabled", "last_admin"]
    with sessions() as db:
        active_admins = db.scalar(
            select(func.count()).select_from(AuthUser).where(AuthUser.role == "admin", AuthUser.status == "active")
        )
    assert active_admins == 1
    engine.dispose()


def test_admin_bootstrap_creates_only_first_admin_without_echoing_password(monkeypatch, db_session) -> None:
    from app import cli

    db_session.execute(delete(AuthSession))
    db_session.execute(delete(AuthUser))
    db_session.flush()
    prompts = iter(("FirstAdmin", "first@example.test", "correct horse battery staple"))
    monkeypatch.setattr(cli.typer, "prompt", lambda *args, **kwargs: next(prompts))
    monkeypatch.setattr(cli, "session_scope", lambda: _single_session_scope(db_session))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["auth-bootstrap-admin"])

    assert result.exit_code == 0, result.output
    assert "correct horse" not in result.output
    assert "$argon2id$" not in result.output
    assert db_session.scalar(__import__("sqlalchemy").select(AuthUser).where(AuthUser.role == "admin")) is not None
    assert runner.invoke(cli.app, ["auth-bootstrap-admin"]).exit_code != 0


def test_bootstrap_first_admin_serializes_competing_database_sessions(tmp_path) -> None:
    from app.models import AuthBootstrapGuard
    from app.services.auth_service import AuthService, BootstrapAdminExistsError

    engine = create_engine(
        f"sqlite:///{(tmp_path / 'bootstrap-race.sqlite3').as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    barrier = Barrier(2)
    result_lock = Lock()
    outcomes: list[str] = []

    def bootstrap(username: str) -> None:
        try:
            with sessions.begin() as db:
                barrier.wait(timeout=5)
                created = AuthService().bootstrap_first_admin(
                    db, username=username, password="correct horse battery staple"
                )
                with result_lock:
                    outcomes.append(created.username)
        except BootstrapAdminExistsError:
            with result_lock:
                outcomes.append("rejected")

    workers = [Thread(target=bootstrap, args=(name,)) for name in ("first-admin", "second-admin")]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=15)

    assert all(not worker.is_alive() for worker in workers)
    assert outcomes.count("rejected") == 1
    assert len(outcomes) == 2
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(AuthUser)) == 1


        assert db.get(AuthBootstrapGuard, 1) is not None


def test_postgres_bootstrap_first_admin_serializes_alembic_schema() -> None:
    database_url, skip_reason = _isolated_postgres_test_url()
    if not database_url:
        pytest.skip(skip_reason)

    result = _alembic_for_test_database(database_url, "upgrade", "head")
    assert result.returncode == 0, result.stderr

    engine = create_engine(database_url, pool_pre_ping=True)
    sessions = sessionmaker(bind=engine)
    with sessions.begin() as db:
        db.execute(delete(AuthSession))
        db.execute(delete(AuthUser))

    barrier = Barrier(2)
    result_lock = Lock()
    outcomes: list[str] = []

    def bootstrap(username: str) -> None:
        from app.services.auth_service import AuthService, BootstrapAdminExistsError

        try:
            with sessions.begin() as db:
                barrier.wait(timeout=10)
                created = AuthService().bootstrap_first_admin(
                    db, username=username, password="correct horse battery staple"
                )
                with result_lock:
                    outcomes.append(created.username)
        except BootstrapAdminExistsError:
            with result_lock:
                outcomes.append("rejected")

    workers = [Thread(target=bootstrap, args=(name,)) for name in ("pg-first-admin", "pg-second-admin")]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=30)

    assert all(not worker.is_alive() for worker in workers)
    assert outcomes.count("rejected") == 1
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(AuthUser)) == 1
    engine.dispose()


@pytest.mark.parametrize(
    ("database_url", "app_env", "destructive_opt_in", "expected_reason"),
    [
        ("postgresql://user:password@localhost/fund_decision", "test", "1", "test/scratch/ci"),
        ("postgresql://user:password@localhost/fund_test", "development", "1", "APP_ENV=test"),
        ("postgresql://user:password@localhost/fund_test", "test", "", "ALLOW_DESTRUCTIVE_TEST_DATABASE=1"),
        ("sqlite:///fund_test.sqlite3", "test", "1", "PostgreSQL"),
    ],
)
def test_postgres_concurrency_target_requires_explicit_isolated_opt_in(
    monkeypatch: pytest.MonkeyPatch,
    database_url: str,
    app_env: str,
    destructive_opt_in: str,
    expected_reason: str,
) -> None:
    monkeypatch.setenv("TEST_POSTGRES_URL", database_url)
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("ALLOW_DESTRUCTIVE_TEST_DATABASE", destructive_opt_in)

    accepted, reason = _isolated_postgres_test_url()

    assert accepted is None
    assert expected_reason in reason


def test_postgres_concurrency_target_accepts_explicit_test_database(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = "postgresql://localhost/fund_auth_test"
    monkeypatch.setenv("TEST_POSTGRES_URL", database_url)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ALLOW_DESTRUCTIVE_TEST_DATABASE", "1")

    accepted, reason = _isolated_postgres_test_url()

    assert accepted == database_url
    assert reason == ""


class _single_session_scope:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc, traceback):
        if exc_type is None:
            self.session.commit()
        else:
            self.session.rollback()
        return False


def _alembic_for_test_database(database_url: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    project_root = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    environment.update(
        {
            "APP_ENV": "test",
            "AUTH_ENABLED": "false",
            "MARKET_PROVIDER": "mock",
            "AUTO_CREATE_SCHEMA": "false",
            "ALEMBIC_DATABASE_URL": database_url,
            "PYTHONPATH": str(project_root / "backend"),
        }
    )
    return subprocess.run(
        [
            sys.executable,
            "-c",
            f"from alembic.config import main; main(argv={['-c', 'alembic.ini', *arguments]!r})",
        ],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def _isolated_postgres_test_url() -> tuple[str | None, str]:
    database_url = os.environ.get("TEST_POSTGRES_URL", "").strip()
    if not database_url:
        return None, "TEST_POSTGRES_URL is not configured"
    if os.environ.get("APP_ENV", "").strip().casefold() != "test":
        return None, "APP_ENV=test is required for destructive PostgreSQL concurrency testing"
    if os.environ.get("ALLOW_DESTRUCTIVE_TEST_DATABASE", "").strip() != "1":
        return None, "ALLOW_DESTRUCTIVE_TEST_DATABASE=1 is required for destructive PostgreSQL concurrency testing"
    try:
        parsed = make_url(database_url)
    except Exception:
        return None, "TEST_POSTGRES_URL is not a valid PostgreSQL test URL"
    if not parsed.drivername.startswith("postgresql"):
        return None, "TEST_POSTGRES_URL must use a PostgreSQL driver"
    database_name = (parsed.database or "").casefold()
    if re.search(r"(?:^|[_-])(?:test|scratch|ci)$", database_name) is None:
        return None, "TEST_POSTGRES_URL database must end in test/scratch/ci"
    return database_url, ""


def test_auth_migration_is_chained_from_current_head_and_has_safe_constraints() -> None:
    from pathlib import Path

    migration = (
        Path(__file__).parents[1] / "alembic" / "versions" / "0a9b1c2d3e4f_multi_user_auth_foundation.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision: str | None = "f7a8b9c0d1e2"' in migration
    assert "auth_users" in migration
    assert "auth_sessions" in migration
    assert "password_hash" in migration
    assert "session_hash" in migration
    assert "csrf_hash" in migration
    assert "auth_bootstrap_guard" in migration
    assert "holdings" not in migration
