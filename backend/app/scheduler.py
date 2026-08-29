from __future__ import annotations

import logging
import signal
import time
from datetime import datetime, timedelta

from sqlalchemy import select

from app.core.clock import MarketClock, MarketPhase
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import init_db, session_scope
from app.models import TaskRun
from app.providers.factory import create_provider
from app.services.runtime_service import RuntimeService
from app.services.task_service import TaskBusyError, TaskExecutionError, TaskService

logger = logging.getLogger(__name__)
STOP = False


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


def _due(last: datetime | None, now: datetime, minutes: int) -> bool:
    if last is None:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=now.tzinfo)
    return now - last >= timedelta(minutes=minutes)


def tick() -> dict:
    settings = get_settings()
    provider = create_provider(settings)
    clock = MarketClock(settings.timezone)
    now = clock.now()
    is_trade_day = provider.is_trade_day(now.date())
    phase = clock.phase(now, is_trade_day)
    executed: list[str] = []

    with session_scope() as db:
        runtime = RuntimeService(settings)
        intervals = runtime.get_all(db)
        tasks = TaskService(settings)

        # The first scheduler tick builds the minimum research dataset. On a real
        # provider this may take time, so production operators can run bootstrap
        # manually before starting the scheduler container.
        if _last_success(db, "sync_instruments") is None:
            tasks.run(db, "sync_instruments")
            executed.append("sync_instruments")

        # Market context has its own bounded cadence. It is intentionally an
        # explicit task rather than a side effect of quotes or the full pipeline.
        market_context_minutes = int(settings.market_context_refresh_minutes)
        if _due(
            _last_terminal_attempt(db, "refresh_market_context"), now, market_context_minutes
        ):
            try:
                tasks.run(db, "refresh_market_context")
            except (TaskExecutionError, TaskBusyError) as exc:
                # A context provider is optional; preserve the rest of this tick
                # while the durable failed TaskRun remains the retry marker.
                # TaskBusyError (advisory lock held by another process) must not
                # abort the remaining quotes/signals steps of this tick.
                failure_class = getattr(exc, "failure_class", type(exc).__name__)
                logger.warning("market context refresh failed: %s", failure_class)
            executed.append("refresh_market_context")

        quote_minutes = int(intervals["quote_refresh_minutes"])
        signal_minutes = int(intervals["signal_refresh_minutes"])
        news_minutes = int(
            intervals["lunch_news_refresh_minutes"]
            if phase == MarketPhase.LUNCH
            else intervals["news_refresh_minutes"]
        )

        if clock.price_session_open(now, is_trade_day) and _due(
            _last_success(db, "refresh_quotes"), now, quote_minutes
        ):
            tasks.run(db, "refresh_quotes")
            executed.append("refresh_quotes")

        if clock.signals_allowed(now, is_trade_day) and _due(
            _last_success(db, "refresh_signals"), now, signal_minutes
        ):
            # Intraday indicators still use the most recently settled daily bars;
            # the live quote is used separately in the state machine.
            tasks.run(db, "refresh_signals")
            executed.append("refresh_signals")

        if _due(_last_success(db, "refresh_news"), now, news_minutes):
            tasks.run(db, "refresh_news", since_hours=72)
            executed.append("refresh_news")

        # Refresh official daily bars and all derived layers once after market close.
        # The date check is represented by a 12-hour gate so a restart remains safe.
        if phase == MarketPhase.AFTER_CLOSE and _due(
            _last_success(db, "refresh_bars"), now, 12 * 60
        ):
            tasks.run(db, "refresh_bars", lookback_days=30)
            tasks.run(db, "refresh_indicators")
            tasks.run(db, "refresh_forecasts")
            tasks.run(db, "refresh_signals")
            tasks.run(db, "generate_report")
            executed.extend(
                [
                    "refresh_bars",
                    "refresh_indicators",
                    "refresh_forecasts",
                    "refresh_signals",
                    "generate_report",
                ]
            )
    return {
        "now": now.isoformat(),
        "trade_day": is_trade_day,
        "phase": phase.value,
        "executed": executed,
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
            if result["executed"]:
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
