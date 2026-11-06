"""Event constraints must block unsupported fills and preserve T+1 lots."""
from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest

from app.services.backtest_service import Position
from app.services.constrained_event_execution import ConstrainedEventExecution


CONFIG = {
    "commission_rate": 0.0002, "minimum_commission": 5.0,
    "slippage_rate": 0.0005, "lot_size": 100,
    "max_abs_premium_pct": 2.0,
}
SIGNAL = {
    "single_fund_target_cap": .25, "single_theme_target_cap": .4,
    "small_add_threshold_weight_points": .02,
}


def _frame(**fields):
    start = date(2026, 11, 2)
    dates = [start + timedelta(days=i) for i in range(4)]
    raw = {
        "open": 10.0, "high": 10.2, "low": 9.8, "close": 10.0,
        "volume": 1000.0, "amount": 10000.0,
        "trade_activity_observed": True,
        "execution_price_pit_verified": True, "price_limit_verified": True,
        "limit_up": False, "limit_down": False, "trading_unit_verified": True,
        "theme_pit_verified": True, "theme_l1_pit": "t1",
        "fund_kind_pit_verified": True, "fund_kind_pit": "ETF",
        "cross_border_fund": False,
        "premium_pit_verified": True, "premium_rate_unit": "percent_points",
        "premium_rate": .5,
    }
    raw.update(fields)
    return pd.DataFrame({name: [value] * 4 for name, value in raw.items()}, index=dates)


def _execute(engine, day, idx, targets, frames, pos=None, cash=100000., kind="ETF", theme="t1"):
    positions = pos if pos is not None else {}
    return engine.execute(
        day, idx, targets, frames, positions, cash,
        instruments={code: SimpleNamespace(kind=kind, theme_l1=theme) for code in frames},
        exposure_cap=.7,
    )


def test_verified_fixture_t_plus_one_and_commission_slippage_lot_accounting():
    engine = ConstrainedEventExecution(CONFIG, SIGNAL)
    frame = _frame()
    dates = list(frame.index)
    pos = {}
    cash, trades = _execute(engine, dates[0], 0, {"510300.SH": .21}, {"510300.SH": frame}, pos=pos)
    assert trades and trades[0]["side"] == "buy"
    assert trades[0]["shares"] % 100 == 0
    assert trades[0]["commission"] >= 5.
    assert trades[0]["price"] > 10.
    assert pos["510300.SH"].shares > 0
    after_buy_cash = cash

    cash, trades = _execute(engine, dates[0], 0, {}, {"510300.SH": frame}, pos=pos, cash=cash)
    assert trades == []
    assert cash == after_buy_cash
    assert pos["510300.SH"].shares > 0
    assert any(item["reason"] == "t_plus_one_unsettled_shares" for item in engine.blocked)

    cash, trades = _execute(engine, dates[1], 1, {}, {"510300.SH": frame}, pos=pos, cash=cash)
    assert len(trades) == 1 and trades[0]["side"] == "sell"
    assert trades[0]["price"] < 10.
    assert not pos
    assert cash < 100000.  # roundtrip transaction costs
    assert engine.summary()["actionable"] is False


def test_missing_execution_rights_or_limit_status_blocks_all_orders():
    day = date(2026, 11, 2)
    cases = [
        ({"execution_price_pit_verified": False}, "first_executable_price_pit_unverified"),
        ({"price_limit_verified": False}, "historical_price_limit_evidence_missing"),
        ({"limit_up": True}, "buy_blocked_at_limit_up_or_unknown"),
        ({"trade_activity_observed": False, "volume": 0.}, "suspended_or_unverified_trading_activity"),
        ({"trading_unit_verified": False}, "exchange_lot_unit_unverified"),
        ({"theme_pit_verified": False}, "effective_dated_theme_missing"),
        ({"theme_l1_pit": None}, "effective_dated_theme_missing"),
        ({"fund_kind_pit_verified": False}, "historical_fund_kind_unverified"),
        ({"cross_border_fund": None}, "historical_cross_border_classification_missing"),
    ]
    for fields, issue in cases:
        engine = ConstrainedEventExecution(CONFIG, SIGNAL)
        cash, trades = _execute(
            engine, day, 0, {"510300.SH": .2},
            {"510300.SH": _frame(**fields)},
        )
        assert trades == [], fields
        assert cash == 100000.
        assert engine.summary()["blocked_by_reason"].get(issue) == 1, fields


def test_held_sell_is_blocked_at_limit_down():
    engine = ConstrainedEventExecution(CONFIG, SIGNAL)
    frame = _frame(limit_down=True)
    day = frame.index[1]
    pos = {"510300.SH": Position(shares=100, average_cost=9.5, opened_index=0)}
    cash, trades = _execute(
        engine, day, 1, {}, {"510300.SH": frame}, pos=pos
    )
    assert trades == []
    assert pos["510300.SH"].shares == 100
    assert engine.summary()["blocked_by_reason"]["sell_blocked_at_limit_down_or_unknown"] == 1


def test_lof_premium_absent_or_excessive_blocks_buy():
    day = date(2026, 11, 2)
    for premium, verified, issue in [
        (None, False, "lof_qdii_premium_pit_missing"),
        (2.1, True, "lof_qdii_premium_limit"),
    ]:
        engine = ConstrainedEventExecution(CONFIG, SIGNAL)
        _, trades = _execute(
            engine, day, 0, {"166001.SZ": .2},
            {"166001.SZ": _frame(fund_kind_pit="LOF",
                                   premium_rate=premium, premium_pit_verified=verified)},
            kind="LOF",
        )
        assert not trades
        assert engine.summary()["blocked_by_reason"][issue] == 1


def test_theme_concentration_and_turnover_hysteresis_are_hard_caps():
    day = date(2026, 11, 2)
    engine = ConstrainedEventExecution(CONFIG, SIGNAL)
    frame = _frame()
    _, trades = _execute(
        engine, day, 0,
        {"510300.SH": .2, "512480.SH": .2},
        {"510300.SH": frame, "512480.SH": frame},
        kind="ETF", theme="shared",
    )
    assert trades
    assert sum(t["gross"] for t in trades) <= 40000. + 1e-6

    engine2 = ConstrainedEventExecution(CONFIG, SIGNAL)
    _, trades2 = _execute(
        engine2, day, 0, {"510300.SH": .01},
        {"510300.SH": frame},
    )
    assert not trades2
    assert engine2.summary()["blocked_by_reason"]["turnover_hysteresis"] == 1


def test_suspended_open_spike_cannot_inflate_buying_power():
    dates = list(_frame().index)
    suspended = _frame()
    suspended.loc[dates[1], "open"] = 1000.
    suspended.loc[dates[1], "close"] = 1000.
    suspended.loc[dates[1], "trade_activity_observed"] = False
    suspended.loc[dates[1], "volume"] = 0.
    active = _frame()
    pos = {"510300.SH": Position(shares=100, average_cost=10., opened_index=0)}
    engine = ConstrainedEventExecution(CONFIG, SIGNAL)
    cash, trades = _execute(
        engine, dates[1], 1, {"512480.SH": .2},
        {"510300.SH": suspended, "512480.SH": active},
        pos=pos, cash=10000., theme="t1",
    )
    buys = [trade for trade in trades if trade["side"] == "buy"]
    assert len(buys) == 1
    # Equity=10k cash + last real observed close (100 shares x 10) = 11k,
    # not the fabricated suspended open (100 shares x 1000).
    assert buys[0]["shares"] == 200
    assert pos["510300.SH"].shares == 100
    assert any(item["reason"] == "suspended_or_price_missing" for item in engine.blocked)


def test_execution_refuses_invalid_lots_and_negative_price_from_slippage():
    day = date(2026, 11, 2)
    frame = _frame()
    for config, reason in [
        ({**CONFIG, "lot_size": 0}, "execution_lot_policy_invalid"),
        ({**CONFIG, "lot_size": -1}, "execution_lot_policy_invalid"),
        ({**CONFIG, "lot_size": True}, "execution_lot_policy_invalid"),
        ({**CONFIG, "slippage_rate": 1.5}, "execution_cost_policy_invalid"),
    ]:
        engine = ConstrainedEventExecution(config, SIGNAL)
        with pytest.raises(ValueError, match=reason):
            _execute(engine, day, 0, {"510300.SH": .2}, {"510300.SH": frame})


def test_premium_unit_must_be_explicitly_verified_for_qdii():
    engine = ConstrainedEventExecution(CONFIG, SIGNAL)
    day = date(2026, 11, 2)
    _, trades = _execute(
        engine, day, 0, {"513500.SH": .2},
        {"513500.SH": _frame(fund_kind_pit="QDII-ETF",
                                premium_rate=.03, premium_rate_unit="decimal")},
    )
    assert not trades
    assert engine.summary()["blocked_by_reason"]["lof_qdii_premium_unit_unverified"] == 1


def test_held_position_missing_historical_theme_blocks_new_buys():
    engine = ConstrainedEventExecution(CONFIG, SIGNAL)
    frame_a = _frame(theme_pit_verified=False)
    frame_b = _frame(theme_l1_pit="t2")
    day = date(2026, 11, 3)
    positions = {"510300.SH": Position(shares=100, average_cost=10., opened_index=0)}
    cash, trades = _execute(
        engine, day, 1, {"510300.SH": .1, "512480.SH": .2},
        {"510300.SH": frame_a, "512480.SH": frame_b},
        pos=positions, cash=10000.,
    )
    assert not trades
    assert cash == 10000.
    assert positions["510300.SH"].shares == 100
    assert engine.summary()["blocked_by_reason"]["held_theme_pit_missing"] >= 1
