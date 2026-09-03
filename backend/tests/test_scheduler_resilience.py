from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import app.scheduler as scheduler
from app.core.config import get_settings
from app.services.task_service import TaskExecutionError

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
        def run(self, _db, task_name: str, **_kwargs):
            calls.append(task_name)
            if task_name == "refresh_news":
                raise TaskExecutionError("news-run", "ProviderError")
            return {"status": "succeeded"}

    class Txn:
        commits = 0
        rollbacks = 0

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
    assert executed == ["refresh_quotes"]
    assert failures == [{"task": "refresh_news", "failure_class": "ProviderError"}]
    assert txn.rollbacks == 1
    assert txn.commits == 1


def _run_fake_tick(monkeypatch, db_session, *, now: datetime, fail_tasks: set[str] | None = None):
    calls: list[tuple[str, dict]] = []
    fail_tasks = fail_tasks or set()

    @contextmanager
    def fake_scope():
        yield db_session

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
    holder: list[object | None] = [None]
    result = scheduler._tick_impl(get_settings(), object(), holder)
    return result, calls


def test_tick_honors_quote_refresh_cadence_between_decision_slots(monkeypatch, db_session) -> None:
    result, calls = _run_fake_tick(
        monkeypatch,
        db_session,
        now=datetime(2026, 8, 31, 10, 0, 0, tzinfo=SHANGHAI),
    )
    names = [name for name, _ in calls]
    assert "refresh_quotes" in names
    assert "refresh_decision_board" not in names
    assert result["failures"] == []


def test_tick_prioritizes_recent_decision_slot_and_avoids_duplicate_quote_call(
    monkeypatch, db_session
) -> None:
    result, calls = _run_fake_tick(
        monkeypatch,
        db_session,
        now=datetime(2026, 8, 31, 14, 31, 10, tzinfo=SHANGHAI),
    )
    names = [name for name, _ in calls]
    assert "refresh_decision_board" in names
    assert "refresh_quotes" not in names
    assert names.index("refresh_decision_board") < names.index("refresh_signals")
    assert result["failures"] == []


def test_failed_decision_slot_releases_claim_for_grace_window_retry(monkeypatch, db_session) -> None:
    result, calls = _run_fake_tick(
        monkeypatch,
        db_session,
        now=datetime(2026, 8, 31, 14, 31, 10, tzinfo=SHANGHAI),
        fail_tasks={"refresh_decision_board"},
    )
    assert any(name == "refresh_decision_board" for name, _ in calls)
    assert db_session.get(scheduler.DecisionBoardSlotRun, "20260831-1430") is None
    assert {item["task"] for item in result["failures"]} >= {"refresh_decision_board"}


def test_after_close_pipeline_continues_after_one_layer_and_news_fail(monkeypatch, db_session) -> None:
    result, calls = _run_fake_tick(
        monkeypatch,
        db_session,
        now=datetime(2026, 8, 31, 15, 30, 0, tzinfo=SHANGHAI),
        fail_tasks={"refresh_indicators", "refresh_news"},
    )
    names = [name for name, _ in calls]
    assert "refresh_bars" in names
    assert "refresh_indicators" in names
    assert "refresh_forecasts" in names
    assert "refresh_signals" in names
    assert "generate_report" in names
    assert names.index("refresh_forecasts") > names.index("refresh_indicators")
    assert {item["task"] for item in result["failures"]} >= {
        "refresh_indicators",
        "refresh_news",
    }
