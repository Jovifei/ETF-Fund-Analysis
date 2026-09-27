from __future__ import annotations

import pandas as pd
from app.utils.price_structure import build_price_structures


def _bars(rows: int = 40) -> pd.DataFrame:
    close = [103.0] * rows
    high = [104.0] * rows
    low = [102.0] * rows
    high[10:12] = [106.0, 106.0]
    low[20:22] = [100.0, 100.0]
    return pd.DataFrame({
        "trade_date": pd.bdate_range("2026-01-05", periods=rows).date,
        "open": close,
        "high": high,
        "low": low,
        "close": close,
        "volume": [None] * rows,
        "amount": [None] * rows,
    })


def _box_bars(rows: int = 120) -> pd.DataFrame:
    frame = pd.DataFrame({
        "trade_date": pd.bdate_range("2026-01-05", periods=rows).date,
        "open": [103.0] * rows,
        "high": [104.0] * rows,
        "low": [102.0] * rows,
        "close": [103.0] * rows,
        "volume": [None] * rows,
        "amount": [None] * rows,
    })
    frame.loc[[10, 45, 80, 110], "high"] = 106.0
    frame.loc[[25, 60, 95], "low"] = 100.0
    return frame


def test_equal_extreme_plateau_is_one_pivot_confirmed_two_bars_after_its_end():
    result = build_price_structures(_bars(), instrument="510300.SH", price_basis_id="basis-a")

    highs = [item for item in result["pivots"] if item["side"] == "high"]
    plateau = [item for item in highs if item["price"] == 106.0]

    assert len(plateau) == 1
    assert plateau[0]["origin_at"] == "2026-01-20"
    assert plateau[0]["confirmed_at"] == "2026-01-22"
    assert plateau[0]["touch_id"]


def test_pivot_confirmation_is_absent_from_prefix_before_right_window_closes():
    frame = _bars()
    result = build_price_structures(frame.iloc[:13], instrument="510300.SH", price_basis_id="basis-a")

    assert not [item for item in result["pivots"] if item["side"] == "high" and item["price"] == 106.0]


def test_daily_structure_returns_reason_when_atr_cannot_be_computed():
    frame = _bars()
    result = build_price_structures(frame, instrument="510300.SH", price_basis_id="basis-a", config={"atr_period": 100})

    assert result["qualified"] is False
    assert result["reason"] == "atr_unavailable"
    assert result["atr14"] is None
    assert result["boxes"] == []


def test_box_requires_independent_pivot_touches_and_keeps_unknown_volume_unknown():
    result = build_price_structures(_box_bars(), instrument="510300.SH", price_basis_id="basis-a")

    assert result["qualified"] is True
    assert len(result["boxes"]) == 1
    box = result["boxes"][0]
    assert box["state"] == "confirmed"
    assert box["upper_touch_count"] >= 2
    assert box["lower_touch_count"] >= 2
    assert box["touch_count"] == len(box["source_ids"])
    assert box["volume_confirmation_available"] is False
    assert box["origin_at"] < box["confirmed_at"]


def test_confirmed_box_matches_replay_of_its_confirmation_prefix():
    frame = _box_bars()
    full = build_price_structures(frame, instrument="510300.SH", price_basis_id="basis-a")["boxes"][0]
    prefix = frame.loc[frame["trade_date"].astype(str) <= full["confirmed_at"]]
    replayed = build_price_structures(prefix, instrument="510300.SH", price_basis_id="basis-a")["boxes"][0]

    assert replayed["structure_id"] == full["structure_id"]
    assert replayed["confirmed_at"] == full["confirmed_at"]
    assert replayed["lower"] == full["lower"]
    assert replayed["upper"] == full["upper"]


def test_structure_and_transition_hashes_bind_only_inputs_available_at_each_date():
    frame = _box_bars()
    prefix_hashes = {day.isoformat(): f"prefix-{index}" for index, day in enumerate(frame["trade_date"])}
    first = build_price_structures(frame, instrument="510300.SH", price_basis_id="basis-a",
        input_hash="history-through-latest-a", input_hashes_by_date=prefix_hashes)
    second = build_price_structures(frame, instrument="510300.SH", price_basis_id="basis-a",
        input_hash="history-through-latest-b", input_hashes_by_date=prefix_hashes)
    box = first["boxes"][0]

    assert first["input_hash"] != second["input_hash"]
    assert box["input_hash"] == prefix_hashes[box["confirmed_at"]]
    assert box["input_hash"] == second["boxes"][0]["input_hash"]
    assert box["state_events"][0]["input_hash"] == prefix_hashes[box["confirmed_at"]]


def test_two_settled_closes_confirm_breakout_then_reentry_marks_failure():
    frame = _box_bars(123)
    frame.loc[120, ["open", "low", "close", "high"]] = [107.0, 106.8, 107.0, 107.2]
    frame.loc[121, ["open", "low", "close", "high"]] = [108.0, 107.8, 108.0, 108.2]
    frame.loc[122, ["open", "low", "close", "high"]] = [103.0, 102.8, 103.0, 103.2]

    box = build_price_structures(frame, instrument="510300.SH", price_basis_id="basis-a")["boxes"][0]
    states = [event["state"] for event in box["state_events"]]

    assert "breakout_confirmed" in states
    assert box["state"] == "failed_breakout"
    assert box["valid_until"] == str(frame.loc[122, "trade_date"])


def test_provisional_crossing_is_ephemeral_and_does_not_change_settled_state():
    frame = _box_bars()
    provisional = {"date": "2026-06-22", "high": 108.0, "low": 107.0, "close": 108.0}
    result = build_price_structures(frame, instrument="510300.SH", price_basis_id="basis-a", provisional_bar=provisional)

    box = result["boxes"][0]
    assert box["state"] == "confirmed"
    assert box["intraday_state"]["state"] == "breakout_attempt"
    assert all(event["date"] != provisional["date"] for event in box["state_events"])


def test_identical_duplicate_bars_are_deduplicated_before_pivot_detection():
    frame = _bars()
    frame = pd.concat([frame.iloc[:12], frame.iloc[[11]], frame.iloc[12:]], ignore_index=True)

    result = build_price_structures(frame, instrument="510300.SH", price_basis_id="basis-a")
    highs = [item for item in result["pivots"] if item["side"] == "high" and item["price"] == 106.0]

    assert len(highs) == 1
    assert highs[0]["origin_at"] == "2026-01-20"


def test_conflicting_same_day_bars_and_unexplained_calendar_gaps_are_rejected():
    frame = _bars()
    conflict = frame.iloc[[11]].copy()
    conflict.loc[:, "close"] = 104.0
    duplicate = pd.concat([frame, conflict], ignore_index=True)
    assert build_price_structures(duplicate, instrument="510300.SH", price_basis_id="basis-a")["reason"] == "duplicate_date_conflict"

    missing = frame["trade_date"].iloc[10].isoformat()
    expected = [day.isoformat() for day in frame["trade_date"]]
    result = build_price_structures(frame.iloc[frame.index != 10], instrument="510300.SH", price_basis_id="basis-a", expected_dates=expected)
    assert result["reason"] == "trading_day_gap"
    assert result["missing_dates"] == [missing]

    weekend = frame.copy()
    weekend.loc[len(weekend)] = weekend.iloc[-1].to_dict() | {"trade_date": pd.Timestamp("2026-03-01").date()}
    result = build_price_structures(weekend, instrument="510300.SH", price_basis_id="basis-a", expected_dates=expected)
    assert result["reason"] == "non_trading_day_bar"
    assert result["unexpected_dates"] == ["2026-03-01"]


def test_monotonic_trend_does_not_create_a_box():
    frame = _bars(120)
    close = [100.0 + index * 0.2 for index in range(len(frame))]
    frame["open"] = close
    frame["close"] = close
    frame["high"] = [value + 0.1 for value in close]
    frame["low"] = [value - 0.1 for value in close]

    result = build_price_structures(frame, instrument="510300.SH", price_basis_id="basis-a")

    assert result["boxes"] == []
    assert result["reason"] in {"no_confirmed_pivots", "insufficient_independent_touches"}


def test_new_box_after_failed_breakout_gets_a_new_identity():
    frame = _box_bars(200)
    frame.loc[[130, 150, 170, 190], "high"] = 106.0
    frame.loc[[140, 160, 180], "low"] = 100.0
    frame.loc[120, ["open", "low", "close", "high"]] = [107.0, 106.8, 107.0, 107.2]
    frame.loc[121, ["open", "low", "close", "high"]] = [108.0, 107.8, 108.0, 108.2]
    frame.loc[122, ["open", "low", "close", "high"]] = [103.0, 102.8, 103.0, 103.2]

    boxes = build_price_structures(frame, instrument="510300.SH", price_basis_id="basis-a", config={"candidate_window": 200})["boxes"]

    assert len(boxes) == 2
    assert boxes[0]["state"] == "failed_breakout"
    assert boxes[1]["state"] == "confirmed"
    assert boxes[1]["origin_at"] > boxes[0]["valid_until"]
    assert boxes[1]["structure_id"] != boxes[0]["structure_id"]


def test_settled_close_through_opposite_boundary_invalidates_confirmed_breakout():
    frame = _box_bars(123)
    frame.loc[120, ["open", "low", "close", "high"]] = [107.0, 106.8, 107.0, 107.2]
    frame.loc[121, ["open", "low", "close", "high"]] = [108.0, 107.8, 108.0, 108.2]
    frame.loc[122, ["open", "low", "close", "high"]] = [99.0, 98.0, 99.0, 100.0]

    box = build_price_structures(frame, instrument="510300.SH", price_basis_id="basis-a")["boxes"][0]

    assert box["state"] == "invalidated"
    assert box["valid_until"] == str(frame.loc[122, "trade_date"])


def test_unbroken_box_expires_after_sixty_settled_bars():
    frame = _box_bars(160)

    box = build_price_structures(frame, instrument="510300.SH", price_basis_id="basis-a", config={"candidate_window": 200})["boxes"][0]

    assert box["state"] == "expired"
    confirmed = frame.index[frame["trade_date"].astype(str) == box["confirmed_at"]][0]
    expired = frame.index[frame["trade_date"].astype(str) == box["valid_until"]][0]
    assert expired - confirmed == 60
