from __future__ import annotations

import os
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
