from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Each pytest invocation owns a distinct database and WAL/SHM lifetime.
# Parallel review/CI commands must not unlink another running suite's DB.
DATABASE_TEMP = TemporaryDirectory(prefix="fund-test-database-")
TEST_DB = Path(DATABASE_TEMP.name) / "test_fund_decision.sqlite3"
REPORTS_TEMP = TemporaryDirectory(prefix="fund-test-reports-")
os.environ.update(
    {
        "APP_ENV": "test",
        "AUTH_ENABLED": "false",
        "MARKET_PROVIDER": "mock",
        "ALLOW_MOCK_FALLBACK": "false",
        "DATABASE_URL": f"sqlite:///{TEST_DB}",
        "REPORTS_DIR": REPORTS_TEMP.name,
        "AUTO_CREATE_SCHEMA": "true",
        "PRIVATE_ACCESS_TOKEN": "test-token-is-long-enough",
        "LOG_LEVEL": "WARNING",
    }
)

from app.db.session import get_engine, init_db, session_scope  # noqa: E402
from app.services.task_service import TaskService  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def database():
    try:
        init_db()
        yield
    finally:
        get_engine().dispose()
        try:
            TEST_DB.unlink(missing_ok=True)
        finally:
            DATABASE_TEMP.cleanup()
            REPORTS_TEMP.cleanup()


@pytest.fixture(scope="session")
def bootstrapped(database):
    with session_scope() as db:
        result = TaskService().run(db, "bootstrap", lookback_days=420, report=True)
    return result


@pytest.fixture()
def db_session(database):
    with session_scope() as db:
        yield db
