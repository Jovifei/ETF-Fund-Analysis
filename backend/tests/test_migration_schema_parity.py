from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _alembic(database_url: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    command_arguments = ["-c", "alembic.ini", *arguments]
    environment = os.environ.copy()
    environment.update(
        {
            "APP_ENV": "test",
            "AUTH_ENABLED": "false",
            "MARKET_PROVIDER": "mock",
            "AUTO_CREATE_SCHEMA": "false",
            "DATABASE_URL": database_url,
            "ALEMBIC_DATABASE_URL": database_url,
            "PYTHONPATH": str(PROJECT_ROOT / "backend"),
        }
    )
    return subprocess.run(
        [
            sys.executable,
            "-c",
            f"from alembic.config import main; main(argv={command_arguments!r})",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_alembic_roundtrip_head_matches_orm_metadata_on_fresh_sqlite(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'schema-parity.sqlite3').as_posix()}"
    upgrade = _alembic(database_url, "upgrade", "head")
    assert upgrade.returncode == 0, upgrade.stderr

    downgrade = _alembic(database_url, "downgrade", "base")
    assert downgrade.returncode == 0, downgrade.stderr

    reupgrade = _alembic(database_url, "upgrade", "head")
    assert reupgrade.returncode == 0, reupgrade.stderr

    check = _alembic(database_url, "check")
    assert check.returncode == 0, check.stderr


def test_owner_migration_refuses_downgrade_when_global_holding_uniqueness_would_be_lost(tmp_path: Path) -> None:
    database_path = tmp_path / "ownership-downgrade.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    upgrade = _alembic(database_url, "upgrade", "head")
    assert upgrade.returncode == 0, upgrade.stderr
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            "INSERT INTO auth_users (username, password_hash, role, status) VALUES (?, ?, 'member', 'active')",
            ("first", "$argon2id$placeholder"),
        )
        connection.execute(
            "INSERT INTO auth_users (username, password_hash, role, status) VALUES (?, ?, 'member', 'active')",
            ("second", "$argon2id$placeholder"),
        )
        connection.execute(
            "INSERT INTO instruments (ts_code, symbol, name, kind, enabled, metadata_json) VALUES (?, ?, ?, 'ETF', 1, '{}')",
            ("510300.SH", "510300", "test"),
        )
        connection.execute(
            "INSERT INTO holdings (user_id, instrument_id, shares, cost_price) VALUES (1, 1, 1, 1)"
        )
        connection.execute(
            "INSERT INTO holdings (user_id, instrument_id, shares, cost_price) VALUES (2, 1, 1, 1)"
        )
    downgrade = _alembic(database_url, "downgrade", "0a9b1c2d3e4f")
    assert downgrade.returncode != 0
    assert "cannot downgrade ownership migration" in downgrade.stderr


def test_legacy_null_owner_holding_is_database_unique_at_head(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy-null-owner.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    upgrade = _alembic(database_url, "upgrade", "head")
    assert upgrade.returncode == 0, upgrade.stderr
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO instruments (ts_code, symbol, name, kind, enabled, metadata_json) VALUES (?, ?, ?, 'ETF', 1, '{}')",
            ("510300.SH", "510300", "test"),
        )
        connection.execute("INSERT INTO holdings (instrument_id, shares, cost_price) VALUES (1, 1, 1)")
        with __import__("pytest").raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO holdings (instrument_id, shares, cost_price) VALUES (1, 2, 2)")
