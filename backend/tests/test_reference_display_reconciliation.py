from __future__ import annotations

from app.services.signal_grade_service import assign_grade, classify_macd, classify_rsi


def test_reference_rsi_bands_match_unified_board() -> None:
    cfg = {"rsi_overbought": 70, "rsi_strong": 50, "rsi_oversold": 30}
    assert classify_rsi(72, cfg)["label"] == "超买 · 短期回调风险高"
    assert classify_rsi(55, cfg)["label"] == "正常偏强 · 趋势中段"
    assert classify_rsi(40, cfg)["label"] == "偏弱 · 动能不足"
    assert classify_rsi(25, cfg)["label"] == "超卖 · 反弹概率升高"


def test_reference_macd_labels_do_not_promote_bear_cont_to_reduce() -> None:
    gold = classify_macd({"macd_dif": 0.02, "macd_dea": 0.01, "macd_hist": 0.01}, {"macd_dif": 0.0, "macd_dea": 0.01, "macd_hist": -0.01}, 0.0008)
    assert gold["kind"] == "gold"
    assert gold["label"] == "强势金叉"
    bear = classify_macd({"macd_dif": -0.03, "macd_dea": -0.02, "macd_hist": -0.02}, {"macd_dif": -0.02, "macd_dea": -0.01, "macd_hist": -0.01}, 0.0008)
    assert bear["kind"] == "bear_cont"
    assert bear["label"] == "空头延续"
    assert assign_grade(pct_change=-0.01, volume={"kind": "flat"}, ma={"kind": "mixed"}, macd=bear, kdj={"j": 40, "kind": "healthy", "death": False}, cfg={"j_add_cap": 90, "stall_return": 0.002}) == "可试探"
