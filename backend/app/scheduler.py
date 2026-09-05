from __future__ import annotations

import logging
import signal
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.clock import MarketClock, MarketPhase
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import init_db, session_scope
from app.models import DecisionBoardSlotRun, TaskRun
from app.providers.factory import create_provider
from app.services.decision_board_service import SLOT_TIMES, decision_board_due_slot
from app.services.runtime_service import RuntimeService
from app.services.task_service import TaskBusyError, TaskExecutionError, TaskService
from app.services.trading_calendar_service import TradingCalendarService

logger = logging.getLogger(__name__)
STOP = False
SHANGHAI = ZoneInfo("Asia/Shanghai")
# APScheduler-style misfire grace: if the daemon is delayed by a provider call,
# coalesce all recently missed board slots to the latest one and run it once.
DECISION_BOARD_MISFIRE_GRACE_SECONDS = 180


def _stop(*_: object) -> None:
    global STOP
    STOP = True


def _last_success(db, task_name: str) -> datetime | None:
    return db.scalar(
        select(TaskRun.finished_at)
        .where(TaskRun.task_name == task_name, TaskRun.status == "succeeded")
        .order_by(TaskRun.finished_at.desc())
        .limit(1)
    )


def _last_terminal_attempt(db, task_name: str) -> datetime | None:
    """Return the last completed attempt, regardless of success or failure."""
    return db.scalar(
        select(TaskRun.finished_at)
        .where(
            TaskRun.task_name == task_name,
            TaskRun.status.in_(("succeeded", "failed", "partial")),
            TaskRun.finished_at.is_not(None),
        )
        .order_by(TaskRun.finished_at.desc())
        .limit(1)
    )


def _last_attempt_or_success(db, task_name: str) -> datetime | None:
    """Prefer terminal attempts while preserving older success-based test/caller contracts."""

    terminal = _last_terminal_attempt(db, task_name)
    return terminal if terminal is not None else _last_success(db, task_name)


def _due(last: datetime | None, now: datetime, minutes: int) -> bool:
    if last is None:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=now.tzinfo)
    return now - last >= timedelta(minutes=minutes)


def decision_board_due_slot_with_grace(
    now: datetime,
    *,
    is_trade_day: bool,
    grace_seconds: int = DECISION_BOARD_MISFIRE_GRACE_SECONDS,
) -> str | None:
    """Return the latest exact/recent board slot, coalescing short scheduler delays.

    The persisted slot key is the scheduled Shanghai wall-clock time, not the
    delayed execution time. This preserves idempotence and makes a delayed
    14:31 execution auditable as the 14:30 decision slot.
    """

    exact = decision_board_due_slot(now, is_trade_day=is_trade_day)
    if exact is not None or not is_trade_day or grace_seconds <= 0:
        return exact

    local = now.astimezone(SHANGHAI) if now.tzinfo is not None else now.replace(tzinfo=SHANGHAI)
    if local.weekday() >= 5:
        return None

    candidates: list[datetime] = []
    for slot_text in SLOT_TIMES:
        hour, minute = (int(value) for value in slot_text.split(":", 1))
        candidate = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        lag_seconds = (local - candidate).total_seconds()
        if 0 <= lag_seconds <= grace_seconds:
            candidates.append(candidate)
    if not candidates:
        return None
    selected = max(candidates)
    return f"{selected:%Y%m%d-%H%M}"


def claim_decision_board_slot(db, slot_key: str, now: datetime) -> bool:
    """Durably claim one Shanghai decision-board slot; safe across restarts."""
    if db.get(DecisionBoardSlotRun, slot_key) is not None:
        return False
    try:
        with db.begin_nested():
            db.add(DecisionBoardSlotRun(slot_key=slot_key, claimed_at=now))
            db.flush()
        return True
    except Exception:
        # A concurrent claimant sees the unique key; do not turn scheduler
        # deduplication into a provider/network retry.
        return False


def _release_decision_board_slot(db, slot_key: str) -> None:
    """Release a failed claim so the same slot can retry inside its grace window."""

    claim = db.get(DecisionBoardSlotRun, slot_key)
    if claim is not None:
        db.delete(claim)
        db.flush()


def _run_guarded(
    tasks: TaskService,
    db,
    task_name: str,
    *,
    executed: list[str],
    failures: list[dict[str, str]],
    **kwargs,
) -> bool:
    """Attempt and durably finish one task without killing the whole scheduler tick.

    `executed` keeps the historical meaning "attempted this tick"; `failures` is
    the failed subset. TaskService owns caller rollback and durable failure audit
    recovery. The scheduler commits each success so a later independent task
    failure cannot erase earlier quote/snapshot/after-close work from this tick.
    """

    executed.append(task_name)
    try:
        tasks.run(db, task_name, **kwargs)
        db.commit()
    except (TaskExecutionError, TaskBusyError) as exc:
        failure_class = str(getattr(exc, "failure_class", type(exc).__name__))[:128]
        failures.append({"task": task_name, "failure_class": failure_class})
        logger.warning("scheduler task %s failed: %s", task_name, failure_class)
        return False
    return True


def tick() -> dict:
    settings = get_settings()
    provider = create_provider(settings)
    task_holder: list[object | None] = [None]
    try:
        return _tick_impl(settings, provider, task_holder)
    finally:
        task_service = task_holder[0]
        close = getattr(task_service, "close", None)
        try:
            if callable(close):
                close()
        finally:
            # Preserve original provider cleanup even when a rebound provider's
            # close path reports an error.
            provider.close()


def _tick_impl(settings, provider, task_holder: list[object | None]) -> dict:
    clock = MarketClock(settings.timezone)
    now = clock.now()
    calendar_decision = TradingCalendarService(settings, provider).decision(now.date())
    is_trade_day = calendar_decision.is_trade_day
    phase = clock.phase(now, is_trade_day)
    executed: list[str] = []
    failures: list[dict[str, str]] = []

    with session_scope() as db:
        runtime = RuntimeService(settings)
        intervals = runtime.get_all(db)
        # Persist runtime defaults before any later TaskService failure can reset
        # the caller transaction.
        db.commit()
        # Share the already-created provider with the task service; tick owns
        # this provider and closes it at the request boundary below.
        tasks = TaskService(settings, provider=provider)
        task_holder[0] = tasks

        # The first scheduler tick builds the minimum research dataset. A
        # provider failure is durable in TaskRun and must not permanently stop
        # the daemon from reaching later independent work.
        if _last_success(db, "sync_instruments") is None:
            _run_guarded(
                tasks,
                db,
                "sync_instruments",
                executed=executed,
                failures=failures,
            )

        signal_minutes = int(intervals["signal_refresh_minutes"])
        quote_minutes = int(intervals["quote_refresh_minutes"])
        news_minutes = int(
            intervals["lunch_news_refresh_minutes"]
            if phase == MarketPhase.LUNCH
            else intervals["news_refresh_minutes"]
        )

        # Critical path first. Coalesce a short scheduler delay to the latest
        # unclaimed decision slot before optional market-context/news work.
        slot_key = decision_board_due_slot_with_grace(now, is_trade_day=is_trade_day)
        queued = db.scalar(
            select(TaskRun.run_id)
            .where(TaskRun.task_name == "refresh_decision_board", TaskRun.status == "queued")
            .order_by(TaskRun.started_at)
            .limit(1)
        )
        board_refresh_window = slot_key is not None or queued is not None
        if slot_key is not None and claim_decision_board_slot(db, slot_key, now):
            succeeded = _run_guarded(
                tasks,
                db,
                "refresh_decision_board",
                executed=executed,
                failures=failures,
                refresh_input=True,
                **({"run_id": queued} if queued else {}),
            )
            if not succeeded:
                # TaskService rolls back a failed task, which normally removes an
                # uncommitted claim. Keep this explicit release for TaskBusy and
                # future claim implementations, then persist the release boundary.
                _release_decision_board_slot(db, slot_key)
                db.commit()
        elif queued is not None:
            # Manual refreshes use the same quote → provisional → snapshot path.
            _run_guarded(
                tasks,
                db,
                "refresh_decision_board",
                executed=executed,
                failures=failures,
                run_id=queued,
                refresh_input=True,
            )

        # Honor the existing runtime quote cadence between board slots. A board
        # refresh already fetches quotes itself, so avoid a duplicate provider
        # call while an exact/recent slot or queued manual refresh is active.
        if (
            clock.price_session_open(now, is_trade_day)
            and not board_refresh_window
            and _due(_last_attempt_or_success(db, "refresh_quotes"), now, quote_minutes)
        ):
            _run_guarded(
                tasks,
                db,
                "refresh_quotes",
                executed=executed,
                failures=failures,
            )

        # Market context is optional and cannot block the quote/decision path.
        market_context_minutes = int(settings.market_context_refresh_minutes)
        if _due(
            _last_attempt_or_success(db, "refresh_market_context"), now, market_context_minutes
        ):
            _run_guarded(
                tasks,
                db,
                "refresh_market_context",
                executed=executed,
                failures=failures,
            )

        after_close_due = phase == MarketPhase.AFTER_CLOSE and _due(
            _last_success(db, "refresh_bars"), now, 12 * 60
        )

        if (
            not after_close_due
            and clock.signals_allowed(now, is_trade_day)
            and _due(_last_success(db, "refresh_signals"), now, signal_minutes)
        ):
            # Intraday indicators still use the most recently settled daily bars;
            # live quotes are a separate state-machine input.
            _run_guarded(
                tasks,
                db,
                "refresh_signals",
                executed=executed,
                failures=failures,
            )

        # Refresh official daily bars and derived layers once after market close.
        # Each task owns a durable failure record; one failed layer no longer
        # prevents all remaining independent cleanup/report work in this tick.
        if after_close_due:
            for task_name, kwargs in (
                ("refresh_bars", {"lookback_days": 120}),
                ("refresh_indicators", {}),
                ("refresh_forecasts", {}),
                ("refresh_signals", {}),
                ("refresh_sector_snapshots", {}),
                ("refresh_decision_board", {}),
                ("generate_report", {}),
            ):
                _run_guarded(
                    tasks,
                    db,
                    task_name,
                    executed=executed,
                    failures=failures,
                    **kwargs,
                )

        # News is additive/optional. Gate by the latest terminal attempt so an
        # upstream outage is retried at the configured cadence instead of every
        # 30 seconds; the success fallback preserves existing scheduler callers.
        if _due(_last_attempt_or_success(db, "refresh_news"), now, news_minutes):
            _run_guarded(
                tasks,
                db,
                "refresh_news",
                executed=executed,
                failures=failures,
                since_hours=72,
            )

    return {
        "now": now.isoformat(),
        "trade_day": is_trade_day,
        "trade_day_verified": calendar_decision.verified,
        "calendar_source": calendar_decision.source,
        "phase": phase.value,
        "executed": executed,
        "failures": failures,
    }


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    if not settings.scheduler_enabled:
        logger.warning("scheduler disabled by SCHEDULER_ENABLED=false; waiting without running jobs")
        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)
        while not STOP:
            time.sleep(5)
        return
    if settings.auto_create_schema:
        init_db()
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    logger.info("scheduler started; tick=%ss", settings.scheduler_tick_seconds)
    while not STOP:
        try:
            result = tick()
            if result["executed"] or result["failures"]:
                logger.info("scheduler tick: %s", result)
        except Exception:
            logger.exception("scheduler tick failed")
        for _ in range(max(1, int(settings.scheduler_tick_seconds))):
            if STOP:
                break
            time.sleep(1)
    logger.info("scheduler stopped")


if __name__ == "__main__":
    main()
