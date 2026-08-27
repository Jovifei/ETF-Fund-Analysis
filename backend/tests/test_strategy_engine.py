from __future__ import annotations

from app.services.strategy_engine import evaluate_strategy_families


def test_strategy_engine_detects_multi_family_resonance():
    values = {
        "close": 10.5, "ma20": 10.0, "ma60": 9.5, "macd_hist": 0.12,
        "adx14": 29, "plus_di14": 32, "minus_di14": 14, "rsi14": 61,
        "kdj_j": 72, "roc12": 8.0, "mfi14": 67, "cmf20": 0.16,
        "obv_slope_5": 0.22, "volume_ratio": 1.55, "amount_ratio": 1.45,
        "box_position_20": 1.02, "box_range_20": 0.14, "turtle_entry_20": True,
        "turtle_entry_55": True, "volume_breakout": True, "pullback_ready": False,
        "second_launch": False, "rsrs_zscore": 1.05, "chip_distance_to_peak_pct": 1.2,
        "chip_winner_ratio": 0.62, "chip_concentration_70": 0.12,
        "rps20": 92, "rps60": 86, "rps120": 75, "wr14": -35,
        "td_buy_setup": 0, "td_sell_setup": 0,
    }
    result = evaluate_strategy_families(values)
    assert result.composite_score >= 65
    keys = {item["key"] for item in result.signals}
    assert "trend_following" in keys
    assert "turtle_breakout" in keys
    assert "rps_leader" in keys
    assert "money_flow_confirmation" in keys
    assert result.family_scores["relative_strength"] >= 80


def test_strategy_engine_surfaces_risk_off_evidence():
    values = {
        "close": 8.8, "ma20": 9.4, "ma60": 9.8, "macd_hist": -0.2,
        "adx14": 32, "plus_di14": 11, "minus_di14": 35, "rsi14": 79,
        "kdj_j": 115, "roc12": -10, "mfi14": 30, "cmf20": -0.18,
        "obv_slope_5": -0.2, "volume_ratio": 0.8, "box_position_20": 0.3,
        "box_range_20": 0.2, "rsrs_zscore": -1.3, "chip_distance_to_peak_pct": 15,
        "chip_winner_ratio": 0.91, "chip_concentration_70": 0.2,
        "rps20": 20, "rps60": 25, "rps120": 30, "wr14": -20,
        "td_buy_setup": 0, "td_sell_setup": 9, "false_breakout_risk": True,
    }
    result = evaluate_strategy_families(values)
    assert result.risks
    assert any(item["direction"] == "negative" for item in result.signals)
    assert result.family_scores["trend"] < 50
