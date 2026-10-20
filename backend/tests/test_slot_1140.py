"""11:40 lunch slot: one fast board after the 11:30 morning close.

The same-day 11:30 morning-close quote counts as fresh only for the 11:40
slot window; every existing slot keeps its exact schedule and 8-minute rule.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.workspace import local_dispatch
from app.workspace.local_dispatch import DISPATCH_SLOTS, FULL_SLOTS, dispatch_once, _validate_fast_replay_quotes
from app.workspace.local_job_ledger import LocalJobLedger
from app.workspace.local_schedule import LOCAL_SCHEDULE_SLOTS
from app.workspace.refresh_policy import lunch_close_quote_fresh, intraday_refresh_minutes, session_quote_window_open
from app.workspace import local_stability

TZ = ZoneInfo("Asia/Shanghai")
IDENTITY = {"code_sha": "a" * 40, "config_hash": "b" * 64, "scope_hash": "c" * 64}
EXISTING = ("13:55", "14:20", "14:30", "14:45", "14:50", "14:55", "15:00", "15:15", "16:10")


def at(hh, mm, ss=0, day=21):
    return datetime(2026, 10, day, hh, mm, ss, tzinfo=TZ)


class Calendar:
    def decision(self, day):
        return SimpleNamespace(verified=True, is_trade_day=True)


def test_slot_sets_add_only_1140():
    assert LOCAL_SCHEDULE_SLOTS == ("11:40",) + EXISTING[1:]
    assert DISPATCH_SLOTS == ("11:40",) + EXISTING
    assert FULL_SLOTS == {"13:55", "15:15", "16:10"} and "11:40" not in FULL_SLOTS
    assert local_stability.SLOTS == ("11:40",) + EXISTING
    assert local_stability.FULL_SLOTS == {"13:55", "15:15", "16:10"}
    assert {k: v for k, v in local_stability.DEFAULT_DEADLINES.items() if k != "11:40"} == {
        slot: 600 if slot in {"13:55", "15:15", "16:10"} else 120 for slot in EXISTING}
    assert local_stability.DEFAULT_DEADLINES["11:40"] == 600


def test_lunch_rule_bounds():
    close = at(11, 30, 0)
    assert lunch_close_quote_fresh(close, at(11, 40))
    assert lunch_close_quote_fresh(at(11, 29, 0), at(11, 52))
    assert lunch_close_quote_fresh(close, at(12, 15))
    assert not lunch_close_quote_fresh(close, at(11, 39, 59))      # before the slot
    assert not lunch_close_quote_fresh(close, at(12, 15, 1))       # after the slot window
    assert not lunch_close_quote_fresh(at(11, 28, 59), at(11, 40))  # not the morning close
    assert not lunch_close_quote_fresh(close - timedelta(days=1), at(11, 40))  # other session
    assert not lunch_close_quote_fresh(at(11, 41), at(11, 40))     # future quote
    assert not lunch_close_quote_fresh(None, at(11, 40))
    # Other slots never relax.
    for slot in EXISTING:
        hh, mm = map(int, slot.split(":"))
        reference = at(hh, mm)
        assert not lunch_close_quote_fresh(reference - timedelta(minutes=10), reference)
        assert not lunch_close_quote_fresh(close, reference)


def test_session_cadence_unchanged():
    assert intraday_refresh_minutes(at(11, 40), is_trade_day=True) is None
    assert not session_quote_window_open(at(11, 40), is_trade_day=True)
    assert intraday_refresh_minutes(at(14, 30), is_trade_day=True) == 10


def _quote(when):
    return SimpleNamespace(quote_time=when, fetched_at=when, is_realtime=True, timestamp_verified=True,
                           degraded_reason=None, price=1.0, source="sina:hq_sinajs:v1")


def test_fast_quote_reasons_only_relaxed_for_1140(monkeypatch):
    from app.services import qualification_gate
    from app.workspace.local_compute import _fast_quote_reasons
    monkeypatch.setattr(qualification_gate, "TradingCalendarService",
                        lambda settings: SimpleNamespace(decision=lambda day: SimpleNamespace(verified=True, is_trade_day=True)))
    settings = SimpleNamespace(timezone=TZ, market_provider="public_composite")
    assert _fast_quote_reasons(settings, _quote(at(11, 30)), at(11, 41)) == []
    assert "quote_stale" in _fast_quote_reasons(settings, _quote(at(14, 20)), at(14, 30))
    assert "quote_stale" in _fast_quote_reasons(settings, _quote(at(11, 30)), at(12, 20))
    assert _fast_quote_reasons(settings, _quote(at(14, 25)), at(14, 30)) == []


def test_board_status_only_relaxed_for_1140():
    from app.services.decision_board_service import DecisionBoardService
    indicator = object()
    assert DecisionBoardService._status(indicator, _quote(at(11, 30)), at(11, 41)) == (
        "fresh", "confirmed_indicator_with_verified_quote")
    assert DecisionBoardService._status(indicator, _quote(at(14, 20)), at(14, 30)) == (
        "stale", "quote_stale_at_snapshot_generation")
    assert DecisionBoardService._status(indicator, _quote(at(11, 30)), at(13, 55)) == (
        "stale", "quote_stale_at_snapshot_generation")


def _bundle(observed, fetched):
    quote = {"is_realtime": True, "timestamp_verified": True, "is_mock": False, "source": "sina:hq_sinajs:v1",
             "price": 1.0, "source_time": observed.isoformat(), "fetched_at": fetched.isoformat()}
    return {"manifest": {"universe": ["510300.SH"]},
            "parts": {"overview": {"rows": [{"ts_code": "510300.SH", "quote": dict(quote)}]},
                      "details": {"510300.SH": {"quote": dict(quote)}}}}


def test_fast_replay_quote_rule():
    _validate_fast_replay_quotes(_bundle(at(11, 30), at(11, 40, 5)), at(11, 43))
    with pytest.raises(ValueError):
        _validate_fast_replay_quotes(_bundle(at(14, 20), at(14, 30, 5)), at(14, 31))
    with pytest.raises(ValueError):  # fetch itself still must be recent
        _validate_fast_replay_quotes(_bundle(at(11, 30), at(11, 30, 5)), at(11, 43))


def test_dispatch_runs_1140_as_fast_and_later_slots_unchanged(tmp_path):
    calls = []
    def run(mode, **hooks):
        calls.append(mode)
        return 1
    for now in (at(11, 37), at(11, 40, 30)):
        dispatch_once(tmp_path, IDENTITY, calendar=Calendar(), run_job=run,
                      replay=lambda **kw: None, now=lambda now=now: now)
    assert calls == ["fast"]
    ledger = LocalJobLedger(tmp_path)
    for slot, mode in (("13:55", "full"), ("14:30", "fast"), ("15:15", "full"), ("16:10", "full")):
        hh, mm = map(int, slot.split(":"))
        due = ledger.plan_due(at(hh, mm, 30), verified_trading=True, identity=IDENTITY, slots=DISPATCH_SLOTS)
        assert due is not None and due["slot"] == slot
        assert ("full" if slot in FULL_SLOTS else "fast") == mode


def test_1140_missed_after_lateness_does_not_block_1355(tmp_path):
    ledger = LocalJobLedger(tmp_path)
    assert ledger.plan_due(at(12, 1), verified_trading=True, identity=IDENTITY, slots=DISPATCH_SLOTS) is None
    due = ledger.plan_due(at(13, 55, 10), verified_trading=True, identity=IDENTITY, slots=DISPATCH_SLOTS)
    assert due["slot"] == "13:55"
