#!/usr/bin/env python3
"""Initialize 1–3 ETF/LOF records through the audited workspace data pipeline.

The command is intentionally local SQLite only.  It does not start a scheduler,
invoke an LLM, read a token from a command-line argument, or allow Mock data.
Use a process environment / runtime secret configuration for a separately
approved Tushare run; AKShare requires only the optional market dependency.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from secrets import token_hex

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALLOWED_PROVIDERS = {"akshare", "tushare", "public_composite", "composite"}


def validate_provider(provider: str) -> str:
    value = provider.strip().lower()
    if value == "mock":
        raise ValueError("mock provider is forbidden for local real-data initialization")
    if value not in ALLOWED_PROVIDERS:
        raise ValueError("provider must be akshare, tushare, public_composite, or composite")
    return value


def validate_database_url(database_url: str, repository_root: Path) -> str:
    if not database_url.startswith("sqlite:///") or database_url == "sqlite:///:memory:":
        raise ValueError("local initializer requires a file-backed sqlite:/// database URL")
    raw_path = database_url.removeprefix("sqlite:///")
    path = Path(raw_path).resolve()
    if path.is_relative_to(repository_root.resolve()):
        raise ValueError("repository database path is forbidden; use a separate local runtime directory")
    return database_url


def local_runtime_environment(database_url: str, provider: str) -> dict[str, str]:
    return {
        "DATABASE_URL": database_url,
        "MARKET_PROVIDER": provider,
        "ALLOW_MOCK_FALLBACK": "false",
        "ANALYSIS_ENABLED": "false",
        "LLM_ENABLED": "false",
        "SCHEDULER_ENABLED": "false",
        "AUTO_CREATE_SCHEMA": "false",
        "APP_ENV": "development",
    }


def _migrate(environment: dict[str, str]) -> None:
    child_env = os.environ.copy()
    child_env.update(environment)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env=child_env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("alembic_migration_failed")


def run(
    database_url: str,
    provider: str,
    codes: list[str],
    report_path: Path,
    deadline_seconds: int,
) -> dict:
    environment = local_runtime_environment(database_url, provider)
    _migrate(environment)
    os.environ.update(environment)

    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.db.session import session_scope
    from app.models import AuthUser  # noqa: F401 - loads the workspace foreign-key target mapper
    from app.workspace import data_jobs
    from app.workspace.models import WorkspaceDataJob
    from app.workspace.protocol import DataRequest

    payload = DataRequest(task="onboard", codes=codes, lookback_days=420, request_key=token_hex(16))
    with session_scope() as db:
        row, _ = data_jobs.enqueue(db, payload, None)
        job_id = row.job_id
    with session_scope() as db:
        claimed = data_jobs.claim(db)
    if claimed != job_id:
        raise RuntimeError("local_data_job_not_claimed")
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "app.workspace.worker", "--execute", job_id],
            cwd=PROJECT_ROOT,
            env={**os.environ, **environment},
            capture_output=True,
            text=True,
            timeout=deadline_seconds,
            check=False,
        )
        exit_code, deadline_exceeded = completed.returncode, False
    except subprocess.TimeoutExpired:
        exit_code, deadline_exceeded = 124, True
    with session_scope() as db:
        row = db.get(WorkspaceDataJob, job_id)
        if row is None:
            raise RuntimeError("local_data_job_missing")
        if deadline_exceeded and row.status == "running":
            row.status = "failed"
            row.failure_reason = "local_deadline_exceeded"
        result = {
            "provider": provider,
            "codes": codes,
            "job_id": row.job_id,
            "worker_exit_code": exit_code,
            "status": row.status,
            "result": row.result_json or {},
            "failure_reason": row.failure_reason,
            "model_called": False,
            "scheduler_started": False,
        }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded local ETF/LOF real-data initialization")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--provider", default="akshare")
    parser.add_argument("--codes", nargs="+", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--deadline-seconds", type=int, default=180)
    args = parser.parse_args()
    try:
        provider = validate_provider(args.provider)
        database_url = validate_database_url(args.database_url, PROJECT_ROOT)
        codes = [code.strip().upper() for code in args.codes]
        if not 1 <= len(codes) <= 3 or len(set(codes)) != len(codes):
            raise ValueError("codes must contain one to three distinct ETF/LOF codes")
        if not 60 <= args.deadline_seconds <= 600:
            raise ValueError("deadline_seconds must be between 60 and 600")
        result = run(database_url, provider, codes, Path(args.report).resolve(), args.deadline_seconds)
    except Exception as exc:  # intentionally no upstream exception text in shell output
        print(json.dumps({"status": "failed", "failure_class": type(exc).__name__}, ensure_ascii=False))
        return 2
    print(json.dumps({key: result[key] for key in ("status", "provider", "codes", "job_id", "worker_exit_code")}, ensure_ascii=False))
    return 0 if result["status"] in {"succeeded", "partial"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
