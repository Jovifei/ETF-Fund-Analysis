from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from app.services.backtest_service import Position, RotationBacktestService
from app.services.crosscheck_engine import (
    _latest_observed_close,
    _trade_ledger_identity,
)


def _suspended_frame() -> tuple[pd.DataFrame, list[date]]:
    first = date(2026, 1, 5)
    days = [first + timedelta(days=i) for i in range(4)]
    return (
        pd.DataFrame(
            {
                "open": [9.9, 99.0, 80.0, 10.9],
                "high": [10.1, 101.0, 81.0, 11.1],
                "low": [9.8, 98.0, 79.0, 10.8],
                "close": [10.0, 100.0, 80.0, 11.0],
                "volume": [1000.0, 0.0, float("nan"), 1000.0],
                "amount": [10000.0, 0.0, float("nan"), 11000.0],
                "trade_activity_observed": [True, False, False, True],
            },
            index=days,
        ),
        days,
    )


def test_primary_mark_to_market_ignores_inactive_closes_and_uses_last_observed_trade():
    frame, days = _suspended_frame()
    mark = RotationBacktestService._observed_close
    assert mark(frame, days[0]) == 10.0
    assert mark(frame, days[1]) == 10.0
    assert mark(frame, days[2]) == 10.0
    assert mark(frame, days[3], before=True) == 10.0
    assert mark(frame, days[3]) == 11.0
    assert mark(frame, days[0], before=True) is None

    replay_frame = frame.copy()
    replay_frame.index = [d.isoformat() for d in days]
    for day in days:
        assert _latest_observed_close(replay_frame, day.isoformat()) == mark(frame, day)
        assert _latest_observed_close(replay_frame, day.isoformat(), before=True) == mark(
            frame, day, before=True
        )


def test_primary_execution_holds_on_inactive_close_spike_and_refuses_infinite_open():
    frame, days = _suspended_frame()
    service = RotationBacktestService()
    positions = {"TEST.SH": Position(shares=100, average_cost=9.0, opened_index=0)}

    for day in (days[1], days[2]):
        cash, trades = service._execute(
            day, 1, {}, {"TEST.SH": frame}, positions, 10_000.0
        )
        assert cash == 10_000.0
        assert trades == []
        assert positions["TEST.SH"].shares == 100

    unusable = frame.copy()
    unusable.at[days[3], "open"] = float("inf")
    cash, trades = service._execute(
        days[3], 3, {}, {"TEST.SH": unusable}, positions, 10_000.0
    )
    assert cash == 10_000.0
    assert trades == []
    assert positions["TEST.SH"].shares == 100


def test_unobservable_held_position_mark_fails_closed_instead_of_zero_or_cost():
    frame, days = _suspended_frame()
    frame.at[days[0], "trade_activity_observed"] = False
    service = RotationBacktestService()
    held = {"TEST.SH": Position(shares=100, average_cost=9.0, opened_index=0)}
    with pytest.raises(ValueError, match="unpriceable_held_position"):
        service._execute(days[1], 1, {}, {"TEST.SH": frame}, held, 10_000.0)
    assert held["TEST.SH"].shares == 100
    assert _latest_observed_close(
        frame.set_axis([d.isoformat() for d in days]), days[1].isoformat(), before=True
    ) is None


def test_independent_trade_ledger_rejects_same_totals_with_different_fill_identity():
    base = {
        "date": "2026-01-05",
        "ts_code": "A.SH",
        "side": "buy",
        "shares": 100,
        "price": 10.0,
        "gross": 1000.0,
        "commission": 5.0,
    }
    changed = {**base, "ts_code": "B.SH"}
    assert len([base]) == len([changed])
    assert sum(item["gross"] for item in [base]) == sum(
        item["gross"] for item in [changed]
    )
    assert sum(item["commission"] for item in [base]) == sum(
        item["commission"] for item in [changed]
    )
    assert _trade_ledger_identity([base]) != _trade_ledger_identity([changed])
    assert _trade_ledger_identity([base]) == _trade_ledger_identity([{**base}])
