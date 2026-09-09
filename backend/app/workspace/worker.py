"""Single low-frequency worker for bounded, user-enqueued deterministic work.

The HTTP process never owns these loops. A child process has a hard deadline;
only explicitly enumerated application tasks may run. This is not an LLM tool.
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from zoneinfo import ZoneInfo
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import init_db, session_scope
from app.models import AuthUser, Instrument
from app.providers.catalog import catalog_records
from app.services.audit_service import AuditTimer, record_provider_audit
from app.services.decision_board_service import DecisionBoardService
from app.services.task_service import TaskService
from app.services.trading_calendar_service import TradingCalendarService
from app.services.watchlist_service import WatchlistService, classify_theme
from app.workspace import data_jobs, factor_diagnostics, jobs
from app.workspace.config import workspace_settings
from app.workspace.models import WorkspaceDataJob, WorkspacePreference
from app.workspace.protocol import ResearchRequest

logger = logging.getLogger(__name__)
STOP = False


def _stop(*_):
    global STOP
    STOP = True


def sync_catalog(db, provider, *, enable_codes=()):
    wanted = set(enable_codes)
    known = {row.ts_code: row for row in db.scalars(select(Instrument))}
    if wanted and wanted.issubset(known):
        records = []
    else:
        timer, error, records = AuditTimer(), None, []
        try:
            records = catalog_records(provider)
        except Exception as exc:
            error = exc
            raise
        finally:
            record_provider_audit(db, run_id=uuid4().hex, operation="list_etf_catalog", provider=provider, result=records, error=error, latency_ms=timer.elapsed_ms)
    created = 0
    updated = 0
    for record in records:
        row = known.get(record.ts_code)
        if row is None:
            theme, subtheme = classify_theme(record.name)
            row = Instrument(ts_code=record.ts_code, symbol=record.symbol, name=record.name, kind=record.kind, exchange=record.exchange, theme_l1=record.theme_l1 or theme, theme_l2=record.theme_l2 or subtheme, enabled=False, metadata_json={**(record.metadata or {}), "catalog_only": True})
            db.add(row)
            known[row.ts_code] = row
            created += 1
        elif row.kind == record.kind:
            row.name = record.name
            row.metadata_json = {**(row.metadata_json or {}), **(record.metadata or {})}
            updated += 1
    if any(known[code].kind not in {"ETF", "LOF"} for code in wanted & known.keys()):
        raise ValueError("only ETF/LOF can enter workspace research pool")
    if wanted - known.keys():
        raise ValueError("requested ETF missing from catalog")
    active = sum(bool(row.enabled) for row in known.values())
    if active + sum(not known[code].enabled for code in wanted) > 200:
        raise ValueError("tracked universe limit reached")
    for code in wanted:
        known[code].enabled = True
    db.flush()
    summary = {"created": created, "updated": updated, "catalog_count": len(known), "enabled_requested": len(wanted), "scope": "provider_returned_catalog_not_certified_complete", "coverage": getattr(records, "coverage", {}), "synced_at": datetime.now(UTC).isoformat()}
    coverage = summary['coverage']
    # Source fallback supports reading, not proof of all-market completeness.
    if coverage:
        category_missing = any(not value.get('source') for value in coverage.values())
        summary['status'] = 'partial' if category_missing else 'succeeded'
    if records:
        saved = db.get(WorkspacePreference, "system:catalog-discovery")
        if saved is None:
            saved = WorkspacePreference(owner_scope="system:catalog-discovery", user_id=None)
            db.add(saved)
        saved.settings_json = summary
    return summary


def outcome_state(outcome: dict) -> str:
    """Do not turn skipped/partial/failed provider outcomes into green steps."""
    state = outcome.get("status")
    if state in {"failed", "error"}:
        return "failed"
    if state in {"partial", "incomplete", "skipped", "unavailable", "stale"}:
        return "partial"
    if any(outcome.get(key) for key in ("failures", "error", "errors", "failed_steps", "missing", "missing_codes", "skipped", "degraded", "price_only")):
        return "partial"
    return "succeeded"


def task_sequence(kind: str, codes: list[str], lookback: int) -> list[tuple[str, dict]]:
    """Independent capabilities: slow catalogs/news cannot delay price publication."""
    if kind in {"prices", "refresh", "onboard"}:
        seq = [("refresh_bars", {"lookback_days": lookback, "codes": codes or None}),
               ("refresh_indicators", {}), ("refresh_forecasts", {}),
               ("refresh_quotes", {"codes": codes or None}), ("refresh_signals", {}),
               ("refresh_decision_board", {})]
        if kind == "refresh":
            seq += [("refresh_sector_snapshots", {}), ("refresh_market_context", {}), ("refresh_news", {"since_hours": 72})]
        return seq
    return {"quotes": [("refresh_quotes", {"codes": codes or None}), ("refresh_decision_board", {})],
            "news": [("refresh_news", {"since_hours": 72})],
            "context": [("refresh_sector_snapshots", {}), ("refresh_market_context", {})],
            "validate": [("validate_forecasts", {})], "shadow_audit": [("shadow_run_audit", {})]}.get(kind, [])


def execute(job_id: str) -> int:
    # A data job cannot silently bill a model via the legacy news enrichment path.
    settings = get_settings().model_copy(update={"analysis_enabled": False, "llm_enabled": False})
    steps = []
    with session_scope() as db:
        row = db.get(WorkspaceDataJob, job_id)
        if row is None or row.status != "running":
            return 2
        request, owner_id = dict(row.request_json), row.user_id
        from app.services.runtime_service import RuntimeService
        settings = RuntimeService(settings).resolve_settings(db).model_copy(update={"analysis_enabled": False, "llm_enabled": False})
    tasks = None
    failed = False
    try:
        tasks = TaskService(settings)
        kind = request["task"]
        if kind == "factors":
            with session_scope() as db:
                report = factor_diagnostics.run(db, settings)
                row = db.get(WorkspaceDataJob, job_id)
                row.result_json = {"factor_report": report, "steps": []}
                row.status = "succeeded" if report.get("status") == "diagnostic" else "partial"
                row.finished_at = datetime.now(UTC)
            return 0
        if kind in {"prices", "refresh", "quotes"}:
            # Explicit user-owned config is the initial research pool; it is
            # not claimed to be a provider-verified or full-market catalog.
            with session_scope() as db:
                if db.scalar(select(Instrument.id).where(Instrument.enabled.is_(True)).limit(1)) is None:
                    from app.workspace.data_seed import seed_configured_universe
                    seed_configured_universe(db, settings)
        if kind in {"catalog", "onboard"}:
            try:
                with session_scope() as db:
                    outcome = sync_catalog(db, tasks.provider, enable_codes=request.get("codes", []) if kind == "onboard" else ())
                    if kind == "onboard":
                        for code in request["codes"]:
                            WatchlistService(settings).add(db, code=code, user_id=owner_id)
                    steps.append({"task": "catalog", "status": outcome_state(outcome), "summary": outcome})
                    failed |= outcome_state(outcome) != "succeeded"
            except Exception as exc:
                steps.append({"task": "catalog", "status": "failed", "reason": type(exc).__name__})
                failed = True
                if kind == "onboard":
                    raise
        if kind == "catalog":
            sequence = []
        elif kind == "minutes":
            sequence = [("refresh_minute_bars", {"codes": request["codes"], "interval": request.get("interval", "30m")})]
        else:
            sequence = task_sequence(kind, request.get("codes", []), request["lookback_days"])
            if not sequence:
                raise ValueError("unsupported workspace task")
        # No catalog bootstrap is needed when selected instruments are already
        # known. The separate catalog task enrolls nothing by itself.
        for task_name, kwargs in sequence:
            # Each service now gates individual instruments. A failed download
            # keeps old bars with their old source date; it does not hide good
            # instruments or price-only historical charts from this batch.
            with session_scope() as db:
                row = db.get(WorkspaceDataJob, job_id)
                if row.status != "running":
                    return 2
                row.result_json = {"steps": steps, "current_step": task_name}
            try:
                with session_scope() as db:
                    outcome = tasks.run(db, task_name, **kwargs)
                state = outcome_state(outcome)
                partial = state != "succeeded"
                summary = {key: value for key, value in outcome.items() if key in {"inserted", "updated", "unchanged", "instruments", "count", "status", "received", "requested", "missing", "degraded", "realtime", "source_timestamp_verified"} and isinstance(value, (int, float, bool, str))}
                steps.append({"task": task_name, "status": state, "summary": summary})
                failed |= partial
            except Exception as exc:
                failed = True
                steps.append({"task": task_name, "status": "failed", "reason": type(exc).__name__})
        with session_scope() as db:
            row = db.get(WorkspaceDataJob, job_id)
            if row.status == "running":
                row.status = "partial" if failed else "succeeded"
                row.finished_at = datetime.now(UTC)
                row.result_json = {"steps": steps, "models_called": False, "qualification_changed": False}
        return 0
    except Exception as exc:
        with session_scope() as db:
            row = db.get(WorkspaceDataJob, job_id)
            if row and row.status == "running":
                row.status, row.failure_reason = "failed", type(exc).__name__
                row.finished_at, row.result_json = datetime.now(UTC), {"steps": steps}
        return 1
    finally:
        if tasks is not None:
            tasks.close()


def heartbeat():
    with session_scope() as db:
        row = db.get(WorkspacePreference, "system:workspace-worker")
        if row is None:
            row = WorkspacePreference(owner_scope="system:workspace-worker", user_id=None)
            db.add(row)
        row.settings_json = {"last_seen_at": datetime.now(UTC).isoformat(), "version": "workspace-worker-v1"}


def enqueue_daily_reviews():
    cfg, settings = workspace_settings(), get_settings()
    if not cfg.daily_review_enabled or settings.market_provider == "mock":
        return 0
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    if (now.hour, now.minute) < (15, 35):
        return 0
    calendar = TradingCalendarService(settings).decision(now.date())
    if not (calendar.is_trade_day and calendar.verified):
        return 0
    added = 0
    with session_scope() as db:
        board = DecisionBoardService(settings).read_latest(db) or {}
        source_time = board.get("generated_at")
        if not source_time or not board.get("rows"):
            return 0
        generated = datetime.fromisoformat(str(source_time)).astimezone(now.tzinfo)
        if generated.date() != now.date() or (generated.hour, generated.minute) < (15, 0):
            return 0
        prefs = db.scalars(select(WorkspacePreference).where(WorkspacePreference.user_id.is_not(None))).all()
        for pref in prefs:
            user = db.get(AuthUser, pref.user_id)
            if not user or user.status != "active" or not pref.settings_json.get("daily_review"):
                continue
            try:
                with db.begin_nested():
                    _, created = jobs.enqueue(db, settings, ResearchRequest(kind="daily", request_key=f"daily-review-{now:%Y%m%d}"), user.id)
                    added += int(created)
            except jobs.WorkspaceError:
                continue
    return added


def stop_job_process(process):
    """Only terminate the process tree created for this owned data job."""
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    else:
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait(timeout=5)


def monitor_job(process, *, seconds=1800):
    deadline, last_heartbeat = time.monotonic() + seconds, 0.0
    try:
        while process.poll() is None and not STOP and time.monotonic() < deadline:
            if time.monotonic() - last_heartbeat > 15:
                try:
                    heartbeat()
                except OperationalError:
                    # A local SQLite task can hold the writer lock. A failed
                    # heartbeat must never abandon its running child process.
                    logger.warning("workspace heartbeat temporarily unavailable; job remains supervised")
                last_heartbeat = time.monotonic()
            time.sleep(1)
    finally:
        stop_job_process(process)


def run_once() -> bool:
    heartbeat()
    enqueue_daily_reviews()
    if workspace_settings().discovery_enabled and get_settings().market_provider != "mock":
        from app.workspace.discovery import enqueue as enqueue_discovery
        with session_scope() as db:
            enqueue_discovery(db)
    with session_scope() as db:
        job_id = data_jobs.claim(db)
    if job_id is None:
        return False
    process = subprocess.Popen([sys.executable, "-m", "app.workspace.worker", "--execute", job_id], start_new_session=os.name != "nt")
    monitor_job(process)
    with session_scope() as db:
        row = db.get(WorkspaceDataJob, job_id)
        if row and row.status == "running":
            row.status, row.failure_reason = "failed", "worker_interrupted_or_deadline"
            row.finished_at = datetime.now(UTC)
    return True


def main():
    parser = argparse.ArgumentParser(description="Low-frequency ETF workspace worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--execute")
    args = parser.parse_args()
    if args.execute:
        if len(args.execute) != 32 or any(char not in "0123456789abcdef" for char in args.execute):
            return 2
        return execute(args.execute)
    settings = get_settings()
    configure_logging(settings.log_level)
    if settings.auto_create_schema:
        init_db()
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    while not STOP:
        try:
            run_once()
        except Exception as exc:
            logger.warning("workspace worker failed: %s", type(exc).__name__)
        if args.once:
            return 0
        for _ in range(workspace_settings().worker_poll_seconds):
            if STOP:
                break
            time.sleep(1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
