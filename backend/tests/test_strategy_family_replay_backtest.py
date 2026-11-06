"""Isolated fixed-slice replay: no dependency on mutable session bootstrap state."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from app.core.config import Settings
from app.services.signal_service import CandidateSignal, blended_signal_score, raw_signal_target
from app.services.signal_v05_service import SignalV05Service
from app.services.strategy_family_replay_backtest_service import (
    NOT_REPLAYED, StrategyFamilyReplayBacktestService,
)


def _frames():
    # Deterministic, *synthetic* OHLCV. History is bounded before each
    # decision. This proves rule-level replay, not data license / PIT.
    days = pd.bdate_range("2026-01-02", periods=132).date
    frames = {}
    instruments = {}
    for i, code in enumerate(("510300.SH", "512480.SH", "159915.SZ")):
        t = np.arange(len(days), dtype=float)
        close = 2.0 + i * 0.2 + t * (0.003 + i * 0.0008) + 0.02 * np.sin(t / 7)
        volume = 10_000 + 100 * t + i * 1000
        frames[code] = pd.DataFrame({
            "open": close - 0.002, "high": close + 0.01,
            "low": close - 0.02, "close": close, "volume": volume,
            "amount": volume * close, "trade_activity_observed": True,
            "adjust": "none", "source": "synthetic_fixture",
            "fetched_at": "2026-11-06",
        }, index=days)
        instruments[code] = SimpleNamespace(
            id=i + 1, ts_code=code, theme_l1=("theme" + str(i)), kind="ETF"
        )
    return instruments, frames


def test_strategy_family_replay_uses_runtime_family_contract(monkeypatch, tmp_path):
    instruments, frames = _frames()
    settings = Settings(_env_file=None, reports_dir=tmp_path, market_provider="mock")
    service = StrategyFamilyReplayBacktestService(settings)
    # Do not share the session-scoped bootstrapped database with unrelated
    # tests. This was the all-suite order-dependent failure in Stage A.
    def load_frames(db):
        service._instruments = instruments
        return instruments, frames, [], {}, {}
    monkeypatch.setattr(service, "_load_frames", load_frames)
    db = SimpleNamespace(add=lambda *_: None, flush=lambda: None)
    result = service.run(db, run_id="fixed-strategy-family-replay")
    payload = json.loads(Path(result["path"]).read_text(encoding="utf-8"))
    contract = payload["audit"]["strategy_replay_contract"]
    assert contract["status"] == "family_action_projection_partial"
    assert contract["actionable"] is False
    assert contract["calibration_status"] == "not_calibrated"
    assert "forecast_news_holding_state_not_replayed" in contract["reason"]
    assert set(NOT_REPLAYED).issubset(contract["not_replayed"])
    assert payload["qualification"] == "UNKNOWN"
    assert len(payload["decisions"]) >= 1
    assert all(decision["selection"]["not_replayed"] for decision in payload["decisions"])
    assert all(decision["as_of_close"] < decision["execution_date"] for decision in payload["decisions"])
    assert payload["audit"]["event_constraint_audit"]["source_execution_pit_qualified"] is False
    assert payload["audit"]["event_constraint_audit"]["blocked_order_count"] > 0
    assert not payload["trades"], "daily-only fixture must never generate a qualified fill"
    for decision in payload["decisions"]:
        for action in decision["selection"]["actions"].values():
            assert action["action_kind"] in {"entry", "probe", "reduce", "hard_reduce", "observe"}
            assert action["actionable"] is False


def test_projection_uses_exact_runtime_action_rules_for_fixed_inputs():
    """The shared state machine must emit identical state/weights in isolation.

    Forecast/news/real holding history are deliberately excluded from this test.
    """
    settings = Settings(_env_file=None, market_provider="mock")
    runtime = SignalV05Service(settings)
    replay = StrategyFamilyReplayBacktestService(settings)
    instruments = {
        "512480.SH": SimpleNamespace(ts_code="512480.SH", theme_l1="semis", kind="ETF"),
        "510300.SH": SimpleNamespace(ts_code="510300.SH", theme_l1="index", kind="ETF"),
    }
    features = pd.DataFrame({
        "close": [10.0, 8.0],
        "technical_score": [85., 70.], "risk_score": [20., 35.],
        "quality_score": [70., 65.], "data_quality": [90., 90.],
        "risk_reasons": [[], []],
    }, index=["512480.SH", "510300.SH"])
    features.attrs["as_of_date"] = pd.Timestamp("2026-10-23").date()
    weights, details = replay._select(
        features, instruments, {}, 0, 0.7, portfolio_equity=100_000.,
    )
    expected = []
    for code, row in features.iterrows():
        score = blended_signal_score(
            row["technical_score"], row["risk_score"],
            50., 50., 60., row["quality_score"],
        )
        expected.append(CandidateSignal(
            instrument=instruments[code], indicator=None, quote=None,
            forecasts={}, holding=None, current_weight=0., score=score,
            confidence=0., data_quality=90., reasons=[], risks=[],
            theme_score=50., fund_quality_score=row["quality_score"],
            raw_target_weight=raw_signal_target(score, 0., runtime.strategy["signal"]),
            actionable=False,
        ))
    runtime._apply_portfolio_constraints(expected, 0.7)
    for item in expected:
        runtime._label_state(item)
    assert {
        item.instrument.ts_code: item.state for item in expected
    } == {code: event["state"] for code, event in details["actions"].items()}
    assert {
        item.instrument.ts_code: item.first_step_target_weight
        for item in expected if item.first_step_target_weight > 0
    } == weights
