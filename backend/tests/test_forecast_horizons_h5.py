"""明日/3日/7日/一个月/3个月 five-horizon forecast contract (1/3/7/20/60 trading days)."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.services.decision_board_service import HORIZONS, DecisionBoardService
from app.services.forecast_service import similarity_forecast
from app.services.snapshot_contract import SIGNAL_FORECAST_SCORE_WEIGHTS, signal_forecast_score_weights
from app.utils.feature_store import HORIZON_FEATURES, build_feature_frame, feature_columns_for_horizon
from app.utils.horizons import DEFAULT_RESEARCH_HORIZONS, FORECAST_HORIZON_LABELS, aligned_research_horizons

FIVE = (1, 3, 7, 20, 60)


def test_formal_horizons_are_exactly_five_with_chinese_labels():
    strategy = get_settings().load_strategy()
    assert DEFAULT_RESEARCH_HORIZONS == FIVE
    assert tuple(aligned_research_horizons(strategy)) == FIVE
    assert tuple(HORIZONS) == FIVE
    assert FORECAST_HORIZON_LABELS == {1: "明日", 3: "3日", 7: "7日", 20: "一个月", 60: "3个月"}
    assert strategy["forecast"]["minimum_effective_windows"] == 10
    for horizon in FIVE:
        assert horizon in HORIZON_FEATURES
        assert len(feature_columns_for_horizon(horizon)) >= 12


def test_signal_score_weight_moves_from_5_to_7_and_stays_formal():
    assert SIGNAL_FORECAST_SCORE_WEIGHTS == {1: 0.5, 7: 0.3}
    assert signal_forecast_score_weights(get_settings().load_strategy()) == {1: 0.5, 7: 0.3}


def _frame(sessions: int, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 1.0 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, sessions)))
    open_ = close * (1 + rng.normal(0, 0.003, sessions))
    raw = pd.DataFrame({
        "trade_date": pd.bdate_range("2024-01-02", periods=sessions).date,
        "open": open_,
        "high": np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.004, sessions))),
        "low": np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.004, sessions))),
        "close": close,
        "volume": rng.integers(1_000_000, 5_000_000, sessions).astype(float),
        "amount": rng.integers(10_000_000, 50_000_000, sessions).astype(float),
    })
    return build_feature_frame(raw, get_settings().load_strategy()["indicator"]).frame


def _run(frame, horizon, gate):
    return similarity_forecast(
        frame, horizon=horizon, neighbors=80, minimum_neighbors=25, maximum_confidence=55,
        feature_columns=feature_columns_for_horizon(horizon, frame.columns), conformal_alpha=0.2,
        minimum_effective_windows=gate,
    )


def test_long_horizon_without_enough_independent_windows_is_unavailable_not_interpolated():
    frame = _frame(283)  # same depth as the live research DB (~13 months)
    short = _run(frame, 1, 10)
    assert short.expected_return is not None and short.p_up is not None
    assert 0.0 <= short.p_up <= 1.0
    long = _run(frame, 60, 10)
    assert long.expected_return is None and long.p_up is None
    assert long.q10 is None and long.q50 is None and long.q90 is None
    assert long.diagnostics["reason"] == "insufficient_independent_windows"
    assert long.diagnostics["effective_non_overlapping_neighbor_count"] < 10
    assert long.diagnostics["minimum_effective_windows"] == 10


def test_gate_is_opt_in_and_only_the_independence_count_decides():
    frame = _frame(283)
    assert _run(frame, 60, None).expected_return is not None  # legacy callers unchanged
    blocked = _run(frame, 60, 10)
    effective = blocked.diagnostics["effective_non_overlapping_neighbor_count"]
    assert effective >= 1
    passed = _run(frame, 60, effective)  # gate exactly at the observed count passes
    assert passed.expected_return is not None and passed.p_up is not None
    assert passed.diagnostics["effective_non_overlapping_neighbor_count"] == effective


def test_board_forecast_payload_exposes_sample_count_and_unavailable_reason():
    available = SimpleNamespace(
        model_version="m", feature_schema_version="f", config_hash="c", input_hash="i",
        expected_return=0.012, q10=-0.02, q50=0.01, q90=0.04, p_up=0.61, confidence=40.0,
        calibration_status="not_calibrated", as_of_date=date(2026, 10, 21), sample_count=80,
        diagnostics_json={},
    )
    gated = SimpleNamespace(**{**available.__dict__, "expected_return": None, "p_up": None,
                               "q10": None, "q50": None, "q90": None,
                               "diagnostics_json": {"reason": "insufficient_independent_windows"}})
    ok = DecisionBoardService._forecast_payload(available)
    assert ok["sample_count"] == 80 and ok["unavailable_reason"] is None and ok["p_up"] == 0.61
    blocked = DecisionBoardService._forecast_payload(gated)
    assert blocked["expected_return"] is None and blocked["p_up"] is None
    assert blocked["unavailable_reason"] == "insufficient_independent_windows"
    missing = DecisionBoardService._forecast_payload(None)
    assert missing["unavailable_reason"] == "forecast_snapshot_missing"


def test_scenario_path_never_extends_past_ten_sessions_to_bound_bundle_size():
    history = [{"date": "2026-10-21", "close": 1.0}]
    base = {"as_of_date": "2026-10-21", "model_version": "m"}
    forecasts = {str(h): {**base, "expected_return": 0.001 * h} for h in FIVE}
    candles = DecisionBoardService._forecast_scenario(history, forecasts)
    assert len(candles) == 7
    assert candles[-1]["anchor_horizons"] == [1, 3, 7]
