"""Fail-first reproduction tests for P1 audit issues (items 1-6).

These tests reproduce the baseline failure modes before root-cause remediation:
1. Top grade 可加仓 + positive score causing KeyError: 5.
2. NaN / Infinity / boolean True score causing unhandled math exceptions or false score=1.
3. Missing / None volume converted to 0.0 falsely classified as accumulation.
4. Existing structure block attached without verifying ts_code, as_of, interval, schema_version.
5. ATR features ignoring as_of_index, violating prefix invariance.
6. Dow pivots confusing occurrence index, confirmation index, and lag_n available_at index.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PKG_PARENT = REPO_ROOT / "research" / "etf_structure_features"
if str(PKG_PARENT) not in sys.path:
    sys.path.insert(0, str(PKG_PARENT))

from app.research.structure_decision import apply_structure_decision
from app.research.structure_v1 import resolve_structure_v1, structure_v1_from_history
from etf_structure_features.atr_risk import atr_features, wilder_atr14
from etf_structure_features.dow_proxy import confirmed_pivots, dow_phase_from_pivots
from etf_structure_features.wyckoff_proxy import wyckoff_from_ohlcv


def test_reproduce_item1_top_grade_keyerror():
    """Item 1: base_grade '可加仓' (rank 4) with positive shift should not raise KeyError: 5."""
    cfg = {"enabled": True, "weight": 1.0, "max_shift": 1}
    shadow = {"score": 1.0, "signal": "结构偏多"}
    # In buggy code, final_rank becomes 5 -> RANK_GRADE[5] raises KeyError: 5
    res = apply_structure_decision("可加仓", shadow, cfg)
    assert res["final_grade"] == "可加仓"
    assert res["applied"] is False


def test_reproduce_item2_nan_inf_bool_handling():
    """Item 2: NaN, Inf, and boolean True must not cause exceptions or be treated as score 1.0."""
    cfg = {"enabled": True, "weight": 0.5, "max_shift": 1}

    # Boolean True as score
    res_bool = apply_structure_decision("观望", {"score": True, "signal": "结构偏多"}, cfg)
    assert res_bool["applied"] is False
    assert res_bool["final_grade"] == "观望"
    assert res_bool["reason"] in {"no_structure", "invalid_score"}

    # NaN as score
    res_nan = apply_structure_decision("观望", {"score": float("nan"), "signal": "结构偏多"}, cfg)
    assert res_nan["applied"] is False
    assert res_nan["final_grade"] == "观望"
    assert res_nan["reason"] in {"no_structure", "invalid_score"}

    # Inf as score
    res_inf = apply_structure_decision("观望", {"score": float("inf"), "signal": "结构偏多"}, cfg)
    assert res_inf["applied"] is False
    assert res_inf["final_grade"] == "观望"
    assert res_inf["reason"] in {"no_structure", "invalid_score"}

    # Boolean True as weight
    res_bool_w = apply_structure_decision("观望", {"score": 0.8, "signal": "结构偏多"}, {"enabled": True, "weight": True})
    assert res_bool_w["applied"] is False or res_bool_w["weight"] == 0.0

    # NaN as weight
    res_nan_w = apply_structure_decision("观望", {"score": 0.8, "signal": "结构偏多"}, {"enabled": True, "weight": float("nan")})
    assert res_nan_w["applied"] is False


def test_reproduce_item3_none_volume_not_accumulation():
    """Item 3: Missing or zero volume must not be classified as accumulation."""
    n = 30
    opens = [3.0] * n
    highs = [3.05] * n
    lows = [2.95] * n
    closes = [2.96] * n  # pos ≈ 0.10 <= 0.35, ret5 = 0.0 <= 0.01

    # When volumes are all 0.0 (converted from None), bug classified this as 'accumulation'
    phase_zero, score, conf, ev = wyckoff_from_ohlcv(
        opens, highs, lows, closes, [0.0] * n, as_of_index=n - 1
    )
    assert phase_zero != "accumulation", "Missing/zero volume must abstain, not claim accumulation"
    assert phase_zero == "unknown"


def test_reproduce_item4_existing_structure_binding():
    """Item 4: resolve_structure_v1 must reject existing block with mismatched ts_code or as_of."""
    dummy_existing = {
        "schema_version": "structure_v1",
        "ts_code": "510300.SH",
        "as_of": "2026-11-05",
        "name": "300ETF",
        "lag_n": 2,
        "wyckoff_phase": "markup",
        "wyckoff_score": 0.7,
        "wyckoff_confidence": 0.75,
        "dow_phase": "uptrend",
        "dow_score": 0.7,
        "dow_confidence": 0.65,
        "atr14": 0.04,
        "atr_pct": 0.012,
        "atr_risk_bucket": "mid",
        "evidence": [],
        "research_only": True,
    }
    # Passing ts_code="510500.SH" while existing has "510300.SH"
    resolved = resolve_structure_v1(
        existing=dummy_existing,
        ts_code="510500.SH",
        history=None,
    )
    assert resolved is None, "Must reject existing structure block if ts_code mismatches"


def test_reproduce_item5_atr_prefix_invariance():
    """Item 5: ATR calculation at as_of_index must not be influenced by future bars."""
    base_n = 30
    highs = [10.0 + i * 0.1 for i in range(base_n)]
    lows = [9.5 + i * 0.1 for i in range(base_n)]
    closes = [9.8 + i * 0.1 for i in range(base_n)]

    # Compute at as_of_index = 20
    as_of = 20
    atr_hist, pct_hist, b_hist, _ = atr_features(highs[:as_of + 1], lows[:as_of + 1], closes[:as_of + 1], as_of_index=as_of)

    # Now provide full history with wild future bars (bars 21-29)
    wild_highs = list(highs)
    wild_lows = list(lows)
    wild_closes = list(closes)
    for j in range(as_of + 1, base_n):
        wild_highs[j] = 100.0
        wild_lows[j] = 50.0
        wild_closes[j] = 75.0

    atr_future, pct_future, b_future, _ = atr_features(wild_highs, wild_lows, wild_closes, as_of_index=as_of)

    assert atr_future == pytest.approx(atr_hist, rel=1e-6), "Future bars must not alter past ATR"
    assert pct_future == pytest.approx(pct_hist, rel=1e-6), "Future bars must not alter past atr_pct"
    assert b_future == b_hist


def test_reproduce_item6_dow_pivot_available_at_and_confirmation():
    """Item 6: Pivots must distinguish occurrence index, confirmed_index, and available_at_index."""
    # Build a sequence with a clear swing high at index 4 (k=2)
    # 0: 10, 1: 11, 2: 12, 3: 13, 4: 15 (peak), 5: 13, 6: 12, 7: 11
    highs = [10.0, 11.0, 12.0, 13.0, 15.0, 13.0, 12.0, 11.0, 10.0]
    lows = [h - 1.0 for h in highs]
    lag_n = 2
    swing_k = 2
    as_of_index = 8

    pivots = confirmed_pivots(highs, lows, as_of_index=as_of_index, lag_n=lag_n, swing_k=swing_k)
    high_pivots = [p for p in pivots if p["side"] == "high"]
    assert len(high_pivots) >= 1
    p = high_pivots[0]

    # Occurrence index is 4 (the bar with 15.0)
    assert p["index"] == 4
    # Confirmation requires 2 subsequent bars (index 4 + 2 = 6)
    assert p["confirmed_index"] == 6
    # Availability to the decision system requires lag_n=2 bars (index 6 + 2 = 8)
    assert "available_at_index" in p, "Must expose available_at_index"
    assert p["available_at_index"] == 8


# ==============================================================================
# Additional P1 Hardening Tests:
# Prefix invariance, short history, missing volume, anomalous values,
# wrong symbol, wrong interval, duplicate timestamps, unclosed bars, price basis
# ==============================================================================

def test_full_prefix_invariance_dow_and_wyckoff():
    """Prefix invariance across Dow and Wyckoff when future bars are appended."""
    n_base = 35
    opens = [10.0 + (i % 5) * 0.2 for i in range(n_base)]
    highs = [o + 0.3 for o in opens]
    lows = [o - 0.3 for o in opens]
    closes = [o + 0.1 for o in opens]
    volumes = [1000.0 + (i % 3) * 100 for i in range(n_base)]

    as_of = 25
    # Evaluated at as_of=25 with base series
    piv_base = confirmed_pivots(highs, lows, as_of_index=as_of, lag_n=2, swing_k=2)
    wy_base = wyckoff_from_ohlcv(opens, highs, lows, closes, volumes, as_of_index=as_of)

    # Appended with wild future bars (bars 36-60)
    future_n = 25
    ext_opens = opens + [50.0] * future_n
    ext_highs = highs + [60.0] * future_n
    ext_lows = lows + [40.0] * future_n
    ext_closes = closes + [55.0] * future_n
    ext_volumes = volumes + [99999.0] * future_n

    piv_ext = confirmed_pivots(ext_highs, ext_lows, as_of_index=as_of, lag_n=2, swing_k=2)
    wy_ext = wyckoff_from_ohlcv(ext_opens, ext_highs, ext_lows, ext_closes, ext_volumes, as_of_index=as_of)

    assert piv_base == piv_ext, "Dow confirmed pivots at as_of_index must be prefix-invariant"
    assert wy_base[0] == wy_ext[0], "Wyckoff phase at as_of_index must be prefix-invariant"
    assert wy_base[1] == pytest.approx(wy_ext[1], rel=1e-6)
    assert wy_base[2] == pytest.approx(wy_ext[2], rel=1e-6)


def test_short_history_fail_closed():
    """Short history (< min_bars) must fail closed without dividing by zero or raising exceptions."""
    assert structure_v1_from_history(ts_code="510300.SH", history=None) is None
    assert structure_v1_from_history(ts_code="510300.SH", history=[]) is None
    short_hist = [{"date": f"2026-11-0{i}", "open": 3.0, "high": 3.1, "low": 2.9, "close": 3.0, "volume": 100} for i in range(1, 10)]
    assert structure_v1_from_history(ts_code="510300.SH", history=short_hist, min_bars=20) is None

    # Directly in proxies
    wy_short = wyckoff_from_ohlcv([3.0]*5, [3.1]*5, [2.9]*5, [3.0]*5, [100.0]*5, as_of_index=4)
    assert wy_short[0] == "unknown"
    assert wy_short[1] == 0.0

    atr_short = wilder_atr14([3.1]*5, [2.9]*5, [3.0]*5, period=14)
    assert atr_short is None


def test_missing_volume_in_history_soft_fails_wyckoff():
    """When volume is None or zero across all bars, Wyckoff must abstain with unknown."""
    n = 25
    bars = [{"date": f"2026-10-{i:02d}", "open": 3.0, "high": 3.1, "low": 2.9, "close": 3.0, "volume": None} for i in range(1, n + 1)]
    row = structure_v1_from_history(ts_code="510300.SH", history=bars, min_bars=20)
    assert isinstance(row, dict)
    assert row["wyckoff_phase"] == "unknown", "Missing volume must yield unknown wyckoff phase"
    assert row["wyckoff_score"] == 0.0


def test_anomalous_values_and_non_finite_inputs():
    """Anomalous float values (NaN, Inf) in price bars must be handled safely."""
    # When NaN in bars drops valid bars count below min_bars
    bars = [{"date": f"2026-10-{i:02d}", "open": 3.0, "high": 3.1, "low": 2.9, "close": 3.0, "volume": 1000.0} for i in range(1, 22)]
    bars[5]["close"] = float("nan")
    bars[6]["close"] = float("nan")
    # 21 - 2 = 19 < 20 -> must fail closed to None
    assert structure_v1_from_history(ts_code="510300.SH", history=bars, min_bars=20) is None

    # Directly in atr_features with non-finite prices
    atr, atr_p, b, _ = atr_features([float("nan")] * 20, [2.0] * 20, [3.0] * 20, as_of_index=19)
    assert atr is None
    assert b == "unknown"

    # Directly in wilder_atr14 with Inf
    assert wilder_atr14([float("inf")] * 20, [2.0] * 20, [3.0] * 20) is None


def test_wrong_interval_and_period_rejected():
    """resolve_structure_v1 must reject non-1d blocks (e.g. 5m, 1w) for daily resolution."""
    existing_5m = {
        "schema_version": "structure_v1",
        "ts_code": "510300.SH",
        "as_of": "2026-11-05",
        "interval": "5m",
        "name": "300ETF",
        "lag_n": 2,
        "wyckoff_phase": "markup",
        "wyckoff_score": 0.7,
        "wyckoff_confidence": 0.75,
        "dow_phase": "uptrend",
        "dow_score": 0.7,
        "dow_confidence": 0.65,
        "atr14": 0.04,
        "atr_pct": 0.012,
        "atr_risk_bucket": "mid",
        "evidence": [],
        "research_only": True,
    }
    # Should reject the 5m block and attempt to refill from history (which is None here -> returns None)
    out = resolve_structure_v1(existing=existing_5m, ts_code="510300.SH", history=None)
    assert out is None, "Must reject existing block with non-1d interval"


def test_unclosed_forecast_bars_excluded():
    """Bars with is_forecast=True must be excluded from structure calculations."""
    n = 25
    bars = [{"date": f"2026-10-{i:02d}", "open": 3.0, "high": 3.1, "low": 2.9, "close": 3.0, "volume": 1000.0} for i in range(1, n + 1)]
    # Add a forecast bar with extreme values
    bars.append({"date": "2026-10-26", "open": 100.0, "high": 200.0, "low": 50.0, "close": 150.0, "volume": 999999.0, "is_forecast": True})

    row = structure_v1_from_history(ts_code="510300.SH", history=bars, min_bars=20)
    assert isinstance(row, dict)
    assert row["as_of"] == "2026-10-25", "as_of must match the last settled bar, ignoring is_forecast"
    assert row["atr14"] < 5.0, "Forecast bar must not blow up ATR"
