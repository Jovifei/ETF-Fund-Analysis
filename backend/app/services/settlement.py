"""Completion belongs to a settled exchange session and its input generation."""
from datetime import datetime, time, timedelta
from sqlalchemy import select
from app.models import Instrument, TaskRun
from app.services.trading_calendar_service import TradingCalendarService

SETTLEMENT_CUTOFF = time(15, 15)


def settled_session(settings, at=None):
    at = at or datetime.now(settings.timezone)
    local = at.astimezone(settings.timezone) if at.tzinfo else at.replace(tzinfo=settings.timezone)
    day = local.date()
    if local.time().replace(tzinfo=None) < SETTLEMENT_CUTOFF:
        day -= timedelta(days=1)
    return TradingCalendarService(settings).effective_trade_date(day)


def session_refresh_due(db, settings, task_name, now, retry_minutes=15, dependencies=()):
    """Partial attempts back off; yesterday's success cannot complete today.

    A newer input-stage result invalidates derived completion even when both
    refer to the same trade date. No old successful output masks a later failure.
    """
    local = now.astimezone(settings.timezone) if now.tzinfo else now.replace(tzinfo=settings.timezone)
    wall = local.time().replace(tzinfo=None)
    if time(15, 0) < wall < SETTLEMENT_CUTOFF:
        return False
    target = settled_session(settings, now).isoformat()
    run = db.scalar(select(TaskRun).where(TaskRun.task_name == task_name)
        .order_by(TaskRun.started_at.desc(), TaskRun.id.desc()).limit(1))
    if run is None:
        return True
    result = run.result_json or {}
    def localize(value):
        return value.replace(tzinfo=settings.timezone) if value.tzinfo is None else value.astimezone(settings.timezone)
    from app.services.task_outcome import normalize_outcome
    scope_complete = True
    different_scope = False
    if task_name == "refresh_bars":
        # A manual single-code refresh shares the task name with the full
        # scheduled download. Validate identities, not only equal counts.
        expected = set(db.scalars(select(Instrument.ts_code).where(Instrument.enabled.is_(True))))
        coverage = result.get("coverage")
        valid_rows = isinstance(coverage, list) and all(isinstance(row, dict) for row in coverage)
        received = [row.get("ts_code") for row in coverage] if valid_rows else []
        valid_codes = all(isinstance(code, str) for code in received)
        scope_complete = bool(expected and valid_rows and valid_codes
            and len(received) == len(expected) and set(received) == expected
            and all(row.get("complete") is True and row.get("received_through") == target for row in coverage))
        requested = result.get("requested")
        # A subset attempt must not postpone the full pool. A failed full-pool
        # attempt must still back off, even if no per-code rows were returned.
        different_scope = (isinstance(requested, int) and not isinstance(requested, bool)
                           and 0 <= requested < len(expected))
    complete = (scope_complete and run.status == "succeeded" and result.get("target_trade_date") == target
                and result.get("coverage_complete") is True and normalize_outcome(result)["status"] == "succeeded")
    if complete and task_name in OUTPUT_STAGES:
        complete = (result.get("completion_contract") == "settled-output-v106"
                    and result.get("output_scope_hash") == output_scope_hash(db, settings))
    if complete:
        finished = localize(run.finished_at or run.started_at)
        for dependency in dependencies:
            latest = db.scalar(select(TaskRun).where(TaskRun.task_name == dependency,
                TaskRun.status.in_(("succeeded", "partial")), TaskRun.finished_at.is_not(None))
                .order_by(TaskRun.finished_at.desc()).limit(1))
            if latest and localize(latest.finished_at) > finished:
                complete = False
                break
    if complete:
        return False
    last = run.finished_at or run.started_at
    # Unknown legacy outcomes retain backoff; a known older session does not.
    same_or_unknown_target = result.get("target_trade_date") in {None, target}
    if not different_scope and same_or_unknown_target and last is not None and (local - localize(last)).total_seconds() < retry_minutes * 60:
        return False
    return True


OUTPUT_STAGES = frozenset({"refresh_signals", "refresh_decision_board", "generate_report", "refresh_sector_snapshots"})


def output_scope_hash(db, settings):
    from app.utils.hashing import stable_hash
    codes = list(db.scalars(select(Instrument.ts_code).where(Instrument.enabled.is_(True)).order_by(Instrument.ts_code)))
    return stable_hash({"codes": codes, "strategy": settings.load_strategy()})


def stamp_output_completion(db, settings, task_name, result, at):
    """Processing a blocked view succeeds; it does not certify the input data.

    Services with record-coverage contracts keep their own counters and status.
    This adds a separate identity for derived publications that previously had
    no target-session receipt at all. A failed/partial output stays retryable.
    """
    if task_name not in OUTPUT_STAGES:
        return result
    result = dict(result)
    result.setdefault("target_trade_date", settled_session(settings, at).isoformat())
    result["output_scope_hash"] = output_scope_hash(db, settings)
    result["completion_contract"] = "settled-output-v106"
    result["completion_basis"] = "processed_output_not_research_qualification"
    proof = (task_name == "refresh_decision_board" and bool(result.get("snapshot_id"))
             or task_name == "generate_report" and bool(result.get("content_hash"))
             or task_name in {"refresh_signals", "refresh_sector_snapshots"}
             and any(isinstance(result.get(k), int) and not isinstance(result.get(k), bool)
                     and result[k] > 0 for k in ("created", "updated", "inserted", "unchanged")))
    result["coverage_complete"] = result.get("status") == "succeeded" and bool(proof)
    return result
