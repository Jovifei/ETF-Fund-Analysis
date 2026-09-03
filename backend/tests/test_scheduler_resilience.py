from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import app.models  # noqa: F401  # register all ORM tables on Base metadata
import app.scheduler as scheduler
from app.core.config import get_settings
from app.db.base import Base
from app.services.task_service import TaskExecutionError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

SHANGHAI = ZoneInfo("Asia/Shanghai")


def test_decision_board_grace_runs_recent_misfire_and_coalesces_to_latest_slot() -> None:
    assert scheduler.decision_board_due_slot_with_grace(
        datetime(2026, 8, 31, 14, 30, 0, tzinfo=SHANGHAI), is_trade_day=True
    ) == "20260831-1430"
    assert scheduler.decision_board_due_slot_with_grace(
        datetime(2026, 8, 31, 14, 31, 45, tzinfo=SHANGHAI), is_trade_day=True
    ) == "20260831-1430"
    assert scheduler.decision_board_due_slot_with_grace(
        datetime(2026, 8, 31, 14, 36, 30, tzinfo=SHANGHAI), is_trade_day=True
    ) == "20260831-1435"
    assert scheduler.decision_board_due_slot_with_grace(
        datetime(2026, 8, 31, 14, 33, 1, tzinfo=SHANGHAI), is_trade_day=True
    ) is None


def test_decision_board_grace_never_turns_non_trade_day_into_a_slot() -> None:
    assert scheduler.decision_board_due_slot_with_grace(
        datetime(2026, 8, 30, 14, 31, tzinfo=SHANGHAI), is_trade_day=False
    ) is None


def test_guarded_task_failure_does_not_prevent_later_independent_task() -> None:
    calls: list[str] = []

    class Tasks:
        def run(self, db, task_name: str, **_kwargs):
            calls.append(task_name)
            if task_name == "refresh_news":
                # Match TaskService.run's caller-session failure contract.
                db.rollback()
                raise TaskExecutionError("news-run", "ProviderError")
            return {"status": "succeeded"}

    class Txn:
        def __init__(self) -> None:
            self.commits = 0
            self.rollbacks = 0

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

    executed: list[str] = []
    failures: list[dict[str, str]] = []
    tasks = Tasks()
    txn = Txn()
    assert scheduler._run_guarded(
        tasks, txn, "refresh_news", executed=executed, failures=failures
    ) is False
    assert scheduler._run_guarded(
        tasks, txn, "refresh_quotes", executed=executed, failures=failures
    ) is True
    assert calls == ["refresh_news", "refresh_quotes"]
    assert executed == ["refresh_news", "refresh_quotes"]
    assert failures == [{"task": "refresh_news", "failure_class": "ProviderError"}]
    assert txn.rollbacks == 1
    assert txn.commits == 1


def _run_fake_tick(
    monkeypatch,
    *,
    now: datetime,
    fail_tasks: set[str] | None = None,
    success_due: set[str] | None = None,
    terminal_due: set[str] | None = None,
):
    calls: list[tuple[str, dict]] = []
    fail_tasks = set(fail_tasks or ())
    success_due = set(success_due or ())
    terminal_due = set(terminal_due or ())
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    db = Session(bind=engine, autoflush=False, expire_on_commit=False)

    @contextmanager
    def fake_scope():
        yield db

    class FakeCalendar:
        def __init__(self, *_args, **_kwargs):
            pass

        def decision(self, day):
            return SimpleNamespace(day=day, is_trade_day=True, verified=True, source="test:XSHG")

    class FakeTasks:
        def __init__(self, *_args, **_kwargs):
            pass

        def run(self, _db, task_name: str, **kwargs):
            calls.append((task_name, dict(kwargs)))
            if task_name in fail_tasks:
                raise TaskExecutionError(f"{task_name}-run", "ProviderError")
            return {"status": "succeeded"}

        def close(self):
            return None

    monkeypatch.setattr(scheduler, "session_scope", fake_scope)
    monkeypatch.setattr(scheduler, "TradingCalendarService", FakeCalendar)
    monkeypatch.setattr(scheduler, "TaskService", FakeTasks)
    monkeypatch.setattr(scheduler.MarketClock, "now", lambda self: now)
    monkeypatch.setattr(
        scheduler,
        "_last_success",
        lambda _db, task_name: None if task_name in success_due else now,
    )
    monkeypatch.setattr(
        scheduler,
        "_last_terminal_attempt",
        lambda _db, task_name: None if task_name in terminal_due else now,
    )
    try:
        holder: list[object | None] = [None]
        result = scheduler._tick_impl(get_settings(), object(), holder)
        claims = set(db.scalars(select(scheduler.DecisionBoardSlotRun.slot_key)).all())
        return result, calls, claims
    finally:
        db.close()
        engine.dispose()


def test_tick_honors_quote_refresh_cadence_between_decision_slots(monkeypatch) -> None:
    result, calls, _claims = _run_fake_tick(
        monkeypatch,
        now=datetime(2026, 8, 31, 10, 0, 0, tzinfo=SHANGHAI),
        success_due={"refresh_quotes"},
        terminal_due={"refresh_quotes"},
    )
    names = [name for name, _ in calls]
    assert names == ["refresh_quotes"]
    assert "refresh_decision_board" not in names
    assert result["failures"] == []


def test_tick_prioritizes_recent_decision_slot_and_avoids_duplicate_quote_call(monkeypatch) -> None:
    result, calls, claims = _run_fake_tick(
        monkeypatch,
        now=datetime(2026, 8, 31, 14, 31, 10, tzinfo=SHANGHAI),
        success_due={"refresh_signals"},
    )
    names = [name for name, _ in calls]
    assert "refresh_decision_board" in names
    assert "refresh_quotes" not in names
    assert names.index("refresh_decision_board") < names.index("refresh_signals")
    assert "20260831-1430" in claims
    assert result["failures"] == []


def test_failed_decision_slot_releases_claim_for_grace_window_retry(monkeypatch) -> None:
    result, calls, claims = _run_fake_tick(
        monkeypatch,
        now=datetime(2026, 8, 31, 14, 31, 10, tzinfo=SHANGHAI),
        fail_tasks={"refresh_decision_board"},
    )
    assert any(name == "refresh_decision_board" for name, _ in calls)
    assert "20260831-1430" not in claims
    assert {item["task"] for item in result["failures"]} >= {"refresh_decision_board"}


def test_after_close_pipeline_continues_after_one_layer_and_news_fail(monkeypatch) -> None:
    result, calls, _claims = _run_fake_tick(
        monkeypatch,
        now=datetime(2026, 8, 31, 15, 30, 0, tzinfo=SHANGHAI),
        fail_tasks={"refresh_indicators", "refresh_news"},
        success_due={"refresh_bars", "refresh_news"},
        terminal_due={"refresh_news"},
    )
    names = [name for name, _ in calls]
    assert "refresh_bars" in names
    assert "refresh_indicators" in names
    assert "refresh_forecasts" in names
    assert "refresh_signals" in names
    assert "generate_report" in names
    assert "refresh_news" in names
    assert names.index("refresh_forecasts") > names.index("refresh_indicators")
    assert {item["task"] for item in result["failures"]} >= {
        "refresh_indicators",
        "refresh_news",
    }
