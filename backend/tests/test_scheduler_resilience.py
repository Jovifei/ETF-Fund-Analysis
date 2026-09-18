from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from uuid import uuid4

import app.models  # noqa: F401  # register all ORM tables on Base metadata
import app.scheduler as scheduler
from app.core.config import get_settings
from app.db.base import Base
from app.models import Instrument, TaskRun
from app.services.task_service import TaskExecutionError
from app.workspace.refresh_policy import intraday_refresh_minutes
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

SHANGHAI = ZoneInfo("Asia/Shanghai")


def test_intraday_refresh_policy_matches_session_cadence() -> None:
    cases = [
        (datetime(2026, 8, 31, 9, 20, tzinfo=SHANGHAI), None),
        (datetime(2026, 8, 31, 9, 30, tzinfo=SHANGHAI), 60),
        (datetime(2026, 8, 31, 10, 30, tzinfo=SHANGHAI), 60),
        (datetime(2026, 8, 31, 11, 30, tzinfo=SHANGHAI), 60),
        (datetime(2026, 8, 31, 12, 0, tzinfo=SHANGHAI), None),
        (datetime(2026, 8, 31, 13, 0, tzinfo=SHANGHAI), 30),
        (datetime(2026, 8, 31, 14, 20, tzinfo=SHANGHAI), 30),
        (datetime(2026, 8, 31, 14, 30, tzinfo=SHANGHAI), 10),
        (datetime(2026, 8, 31, 14, 48, tzinfo=SHANGHAI), 10),
        (datetime(2026, 8, 31, 14, 50, tzinfo=SHANGHAI), 2),
        (datetime(2026, 8, 31, 14, 58, tzinfo=SHANGHAI), 2),
        (datetime(2026, 8, 31, 15, 1, tzinfo=SHANGHAI), None),
        (datetime(2026, 8, 30, 14, 50, tzinfo=SHANGHAI), None),
    ]
    assert [intraday_refresh_minutes(value, is_trade_day=value.weekday() < 5) for value, _ in cases] == [expected for _, expected in cases]


def test_decision_board_grace_runs_recent_misfire_and_coalesces_to_latest_slot() -> None:
    assert scheduler.decision_board_due_slot_with_grace(
        datetime(2026, 8, 31, 14, 30, 0, tzinfo=SHANGHAI), is_trade_day=True
    ) == "20260831-1430"
    assert scheduler.decision_board_due_slot_with_grace(
        datetime(2026, 8, 31, 14, 31, 45, tzinfo=SHANGHAI), is_trade_day=True
    ) == "20260831-1430"
    assert scheduler.decision_board_due_slot_with_grace(
        datetime(2026, 8, 31, 14, 41, 30, tzinfo=SHANGHAI), is_trade_day=True
    ) == "20260831-1440"
    assert scheduler.decision_board_due_slot_with_grace(
        datetime(2026, 8, 31, 14, 43, 1, tzinfo=SHANGHAI), is_trade_day=True
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
    is_trade_day: bool = True,
    real_pipeline: bool = False,
    seed=None,
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
            return SimpleNamespace(day=day, is_trade_day=is_trade_day, verified=True, source="test:XSHG")

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

    if not real_pipeline:
        monkeypatch.setattr(scheduler, "settled_pipeline_tasks",
            lambda *a, **k: list(scheduler.DAILY_DEPENDENCIES) if "refresh_bars" in success_due else [])
        monkeypatch.setattr("app.services.settlement.session_refresh_due", lambda *a, **k: False)
    if seed is not None:
        seed(db)
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


def test_tick_skips_quotes_during_lunch_and_open_auction(monkeypatch) -> None:
    for now in (
        datetime(2026, 8, 31, 9, 20, tzinfo=SHANGHAI),
        datetime(2026, 8, 31, 12, 15, tzinfo=SHANGHAI),
    ):
        result, calls, claims = _run_fake_tick(
            monkeypatch,
            now=now,
            success_due={"refresh_quotes", "refresh_signals"},
            terminal_due={"refresh_quotes", "refresh_signals"},
        )
        names = [name for name, _ in calls]
        assert "refresh_quotes" not in names
        assert "refresh_decision_board" not in names
        assert claims == set()
        assert result["trade_day"] is True
        assert result["failures"] == []


def test_tick_does_not_claim_slots_or_fake_success_on_non_trade_days(monkeypatch) -> None:
    result, calls, claims = _run_fake_tick(
        monkeypatch,
        now=datetime(2026, 8, 30, 14, 50, tzinfo=SHANGHAI),
        success_due={"refresh_quotes", "refresh_decision_board"},
        terminal_due={"refresh_quotes", "refresh_decision_board"},
        is_trade_day=False,
    )
    names = [name for name, _ in calls]
    assert "refresh_quotes" not in names
    assert "refresh_decision_board" not in names
    assert claims == set()
    assert result["trade_day"] is False
    assert result["phase"] == "closed"


def test_tick_fires_1450_decision_slot_on_two_minute_cadence(monkeypatch) -> None:
    result, calls, claims = _run_fake_tick(
        monkeypatch,
        now=datetime(2026, 8, 31, 14, 50, 5, tzinfo=SHANGHAI),
    )
    names = [name for name, _ in calls]
    assert "refresh_decision_board" in names
    assert "refresh_quotes" not in names
    assert "20260831-1450" in claims
    assert result["failures"] == []


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


def test_tick_after_close_runs_board_when_upstream_succeeded_and_only_intraday_board_exists(monkeypatch) -> None:
    settings = get_settings()
    slot_at = datetime(2026, 8, 31, 14, 50, tzinfo=SHANGHAI)
    eod = datetime(2026, 8, 31, 16, 5, tzinfo=SHANGHAI)

    def seed(db):
        from app.services.settlement import stamp_output_completion, settled_session

        db.add(Instrument(ts_code="998801.SH", symbol="998801", kind="ETF", name="catch-up", enabled=True))
        db.flush()

        def stamp(name, at, **extra):
            target = settled_session(settings, at).isoformat()
            result = {
                "status": "succeeded",
                "requested": 1,
                "completed": 1,
                "coverage_complete": True,
                "target_trade_date": target,
                **extra,
            }
            if name == "refresh_bars":
                result["coverage"] = [{"ts_code": "998801.SH", "complete": True, "received_through": target}]
            if name == "refresh_decision_board":
                result["snapshot_id"] = "intraday-1450"
            if name in {"refresh_signals", "refresh_sector_snapshots"}:
                result["created"] = 1
            result = stamp_output_completion(db, settings, name, result, at)
            db.add(TaskRun(
                run_id=uuid4().hex,
                task_name=name,
                status=result["status"],
                started_at=at,
                finished_at=at,
                result_json=result,
            ))
            db.flush()

        stamp("refresh_decision_board", slot_at)
        for offset, name in enumerate(("refresh_bars", "refresh_indicators", "refresh_forecasts", "refresh_signals")):
            stamp(name, eod.replace(hour=15, minute=20 + offset))

    result, calls, claims = _run_fake_tick(
        monkeypatch,
        now=eod,
        real_pipeline=True,
        seed=seed,
    )
    names = [name for name, _ in calls]
    assert "refresh_bars" not in names
    assert "refresh_indicators" not in names
    assert "refresh_forecasts" not in names
    assert "refresh_decision_board" in names
    assert "generate_report" in names
    assert claims == set()
    assert result["trade_day"] is True
    assert result["failures"] == []
