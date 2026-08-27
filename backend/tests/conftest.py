from __future__ import annotations

import os
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DB = PROJECT_ROOT / "backend" / "tests" / "test_fund_decision.sqlite3"
TEST_DB.unlink(missing_ok=True)
os.environ.update(
    {
        "APP_ENV": "test",
        "AUTH_ENABLED": "false",
        "MARKET_PROVIDER": "mock",
        "ALLOW_MOCK_FALLBACK": "false",
        "DATABASE_URL": f"sqlite:///{TEST_DB}",
        "AUTO_CREATE_SCHEMA": "true",
        "PRIVATE_ACCESS_TOKEN": "test-token-is-long-enough",
        "LOG_LEVEL": "WARNING",
    }
)

from app.db.session import init_db, session_scope  # noqa: E402
from app.services.task_service import TaskService  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def database():
    init_db()
    yield
    TEST_DB.unlink(missing_ok=True)


@pytest.fixture(scope="session")
def bootstrapped(database):
    with session_scope() as db:
        result = TaskService().run(db, "bootstrap", lookback_days=420, report=True)
    return result


@pytest.fixture()
def db_session(database):
    with session_scope() as db:
        yield db
