from __future__ import annotations

from app.services.strategy_replay_contract import build_strategy_replay_contract


def test_strategy_replay_contract_is_stable_and_fail_closed():
    strategy = {
        "version": "strategy-v1",
        "strategy_engine": {
            "version": "family-v1",
            "family_weights": {"trend": 0.5, "momentum": 0.5},
        },
        "signal": {
            "entry_score": 68,
            "probe_score": 58,
            "reduce_score": 38,
            "hard_reduce_score": 28,
        },
    }
    result = build_strategy_replay_contract(
        strategy,
        status="runtime_observation",
        source="test",
        feature_basis="settled_daily_bars",
        as_of="2026-11-06",
        family_scores={"trend": 70, "momentum": 60},
        composite_score=65,
    )
    assert result["identity_hash"]
    assert result["family_scores"]["trend"] == 70
    assert result["family_scores"]["reversal"] is None
    assert result["qualification"] == "UNKNOWN"
    assert result["actionable"] is False
    assert result["calibration_status"] == "not_calibrated"
