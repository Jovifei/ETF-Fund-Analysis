from __future__ import annotations

from copy import deepcopy

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


def test_replay_identity_covers_versions_weights_indicators_and_risk_controls():
    base = {
        "version": "runtime-A",
        "indicator_version": "ind-A",
        "forecast_version": "forecast-A",
        "backtest_version": "ledger-A",
        "strategy_replay_version": "replay-A",
        "indicator": {"ma_windows": [5, 20, 60]},
        "strategy_engine": {"version": "family-A", "family_weights": {"trend": .5}},
        "signal": {"entry_score": 68, "single_theme_target_cap": .40,
                   "portfolio_exposure_caps": {"high_risk": .4}},
        "backtest": {"commission_rate": .0002},
        "forecast": {"horizons": [1, 7]},
    }
    def identity(cfg):
        return build_strategy_replay_contract(
            cfg, status="runtime_observation", source="test",
            feature_basis="settled_daily_bars",
        )["identity_hash"]
    first = identity(base)
    assert first == identity(deepcopy(base))
    mutations = [
        ("version", "runtime-B"),
        ("indicator_version", "ind-B"),
        ("forecast_version", "forecast-B"),
        ("strategy_replay_version", "replay-B"),
        ("backtest_version", "ledger-B"),
    ]
    for key, new_value in mutations:
        changed = deepcopy(base)
        changed[key] = new_value
        assert identity(changed) != first, key
    for section, key, value in [
        ("indicator", "ma_windows", [5, 30, 60]),
        ("strategy_engine", "family_weights", {"trend": .4}),
        ("signal", "single_theme_target_cap", .3),
        ("signal", "portfolio_exposure_caps", {"high_risk": .2}),
        ("backtest", "commission_rate", .0005),
        ("forecast", "horizons", [1, 20]),
    ]:
        changed = deepcopy(base)
        changed[section][key] = value
        assert identity(changed) != first, (section, key)
