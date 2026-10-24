from __future__ import annotations

import pytest


def test_strategy_spec_and_result_contracts():
    from app.services.strategy_evaluation.contracts import (
        EvaluationMetrics,
        StrategyResult,
        StrategySpec,
    )

    spec = StrategySpec(
        strategy_id="M0_TSMOM_RAW",
        version="20261024_v2",
        family="trend",
        parameters={"lookback": 252},
        required_fields=["trade_date", "close"],
        execution_policy={"timing": "t_plus_1_open", "t_plus_1_sell": True},
    )
    assert spec.strategy_id == "M0_TSMOM_RAW"
    assert spec.research_only is True
    assert spec.actionable is False

    # Valid research candidate result
    res = StrategyResult(
        strategy_id=spec.strategy_id,
        version=spec.version,
        trade_date="2026-10-23",
        ts_code="510300.SH",
        signal_score=0.085,
        rank_percentile=0.75,
        trend_state=1,
        target_weight=0.25,
        qualification="research_candidate",
        as_of="2026-10-23 15:00:00",
        available_at="2026-10-23 17:00:00",
    )
    assert not res.is_abstain()
    assert res.missing_reason is None
    assert res.target_weight == 0.25
    assert res.research_only is True
    assert res.actionable is False

    # Abstain on missing history - must not disguise as neutral 0.0 or 50.0
    abstain_res = StrategyResult.abstain(
        strategy_id=spec.strategy_id,
        version=spec.version,
        trade_date="2026-10-23",
        ts_code="513500.SH",
        reason="insufficient_lookback_history:bars_count=120_required=252",
        as_of="2026-10-23 15:00:00",
        available_at="2026-10-23 17:00:00",
    )
    assert abstain_res.is_abstain()
    assert abstain_res.signal_score is None
    assert abstain_res.target_weight == 0.0
    assert "insufficient_lookback_history" in str(abstain_res.missing_reason)


def test_evaluation_metrics_separates_direction_and_transaction():
    from app.services.strategy_evaluation.contracts import EvaluationMetrics

    m = EvaluationMetrics(
        strategy_id="mom_120_cs",
        version="20261024_v2",
        sample_name="recent_all_enabled",
        horizon=7,
        date_range=("2025-08-18", "2026-10-23"),
        # Directional prediction
        rank_ic=0.0453,
        ic_days=280,
        direction_hit_rate=0.4631,
        hit_rate_wilson_ci=(0.421, 0.505),
        n_signals=500,
        mean_fwd_long=-0.00197,
        mean_fwd_short=-0.00310,
        # Transaction ledger
        closed_trades=42,
        net_win_rate=0.4524,
        win_rate_wilson_ci=(0.312, 0.601),
        profit_factor=0.92,
        net_expectancy_bps=-12.5,
        annualized_net_return=-0.038,
        annualized_net_sharpe=-0.21,
        max_drawdown=-0.085,
        turnover_annual=4.2,
        cost_bps_roundtrip=20.0,
    )
    d = m.to_dict()
    assert d["rank_ic"] == 0.0453
    assert d["mean_fwd_long"] == -0.00197
    # Direction IC positive while net return and mean long forward return are negative
    assert d["net_expectancy_bps"] < 0
    assert d["research_only"] is True
    assert d["actionable"] is False
