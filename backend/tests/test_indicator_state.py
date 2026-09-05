"""indicator_state 单元测试：存储值 → 展示状态的统一口径。"""
from __future__ import annotations

from app.utils.indicator_state import (
    classify_kdj,
    classify_macd,
    classify_ma,
    classify_rsi,
    classify_td,
    classify_volume,
    kdj_state_view,
    ma_state_view,
    macd_state_view,
    td_state_view,
    thresholds_from_strategy,
    volume_state_view,
)

CFG = thresholds_from_strategy(None)


def test_thresholds_merge_strategy_block():
    merged = thresholds_from_strategy({"signal_grade": {"j_overbought": 95, "unknown_key": 1}})
    assert merged["j_overbought"] == 95
    assert merged["j_add_cap"] == 90  # 默认保留
    assert "unknown_key" not in merged


def test_classify_ma_bull_bear_mixed_and_missing():
    bull = classify_ma({"ma5": 4, "ma10": 3, "ma20": 2, "ma30": 1, "close": 4.1}, None)
    assert bull["kind"] == "bull" and bull["label"] == "多头排列"
    assert [a["dir"] for a in bull["arrows"]] == ["up", "up", "up", "up"]
    bear = classify_ma({"ma5": 1, "ma10": 2, "ma20": 3, "ma30": 4, "close": 0.9}, None)
    assert bear["kind"] == "bear"
    mixed = classify_ma({"ma5": 2, "ma10": 4, "ma20": 3, "ma30": 1}, None)
    assert mixed["kind"] == "mixed"
    assert classify_ma({"ma5": 1}, None)["kind"] == "unknown"


def test_classify_macd_cross_and_states():
    # 金叉：昨日 dif<=dea，今日 dif>dea
    gold = classify_macd(
        {"macd_dif": 0.02, "macd_dea": 0.01, "macd_hist": 0.01},
        {"macd_dif": 0.0, "macd_dea": 0.01, "macd_hist": -0.01},
        CFG["macd_approach_hist"],
    )
    assert gold["kind"] == "gold" and gold["label"] == "强势金叉"
    # 死叉：昨日 dif>=dea，今日 dif<dea
    death = classify_macd(
        {"macd_dif": -0.03, "macd_dea": -0.02, "macd_hist": -0.02},
        {"macd_dif": -0.015, "macd_dea": -0.02, "macd_hist": -0.005},
        CFG["macd_approach_hist"],
    )
    assert death["kind"] == "death"
    # 多头延续（dif>0，hist>0，无交叉）
    cont = classify_macd(
        {"macd_dif": 0.05, "macd_dea": 0.03, "macd_hist": 0.02},
        {"macd_dif": 0.04, "macd_dea": 0.025, "macd_hist": 0.015},
        CFG["macd_approach_hist"],
    )
    assert cont["kind"] == "bull_cont"
    assert classify_macd({"macd_dif": 0.01}, None, 0.0008)["kind"] == "unknown"


def test_classify_kdj_death_overbought_low_healthy():
    death = classify_kdj({"kdj_j": 30, "kdj_k": 40, "kdj_d": 45}, {"kdj_k": 50, "kdj_d": 44}, CFG)
    assert death["death"] is True and death["label"] == "死叉"
    overbought = classify_kdj({"kdj_j": 101, "kdj_k": 80, "kdj_d": 70}, None, CFG)
    assert overbought["kind"] == "overbought"
    low = classify_kdj({"kdj_j": 10, "kdj_k": 30, "kdj_d": 25}, None, CFG)
    assert low["kind"] == "low"
    healthy = classify_kdj({"kdj_j": 55, "kdj_k": 50, "kdj_d": 45}, None, CFG)
    assert healthy["kind"] == "healthy"
    assert classify_kdj({"kdj_j": 50}, None, CFG)["kind"] == "unknown"


def test_classify_volume_rsi_td():
    assert classify_volume(1.2, 1.15, 0.9)["kind"] == "expand"
    assert classify_volume(0.8, 1.15, 0.9)["kind"] == "contract"
    assert classify_volume(1.0, 1.15, 0.9)["kind"] == "flat"
    assert classify_volume(None, 1.15, 0.9)["kind"] == "unknown"
    assert classify_rsi(72, CFG)["label"].startswith("超买")
    assert classify_rsi(55, CFG)["label"].startswith("正常偏强")
    assert classify_rsi(25, CFG)["label"].startswith("超卖")
    assert classify_td({"td_buy_setup": 7}) == {"label": "TD7", "kind": "buy"}
    assert classify_td({"td_sell_setup": 9}) == {"label": "TD9", "kind": "sell"}
    assert classify_td({}) == {"label": "—", "kind": "none"}


def test_view_adapters_shapes():
    ma = ma_state_view({"ma5": 4, "ma10": 3, "ma20": 2, "ma30": 1, "close": 4.1}, None)
    assert ma["bullish"] is True and ma["dirs"][0] == ["M5", "up"] and "MA5=" in ma["vals"]
    macd = macd_state_view(
        {"macd_dif": 0.02, "macd_dea": 0.01, "macd_hist": 0.01},
        {"macd_dif": 0.0, "macd_dea": 0.01, "macd_hist": -0.01},
        CFG,
    )
    assert macd["cls"] == "macd-gold" and "DIF=" in macd["vals"]
    kdj = kdj_state_view({"kdj_j": 101, "kdj_k": 80, "kdj_d": 70}, None, CFG)
    assert kdj["cls"] == "kdj-hot" and kdj["label"] == "J=101.0" and kdj["sub"] == "超买"
    volume = volume_state_view({"volume_ratio": 1.3}, CFG)
    assert volume["text"].startswith("放量") and volume["cls"] == "vol-expand"
    td = td_state_view({"td_sell_setup": 9})
    assert td["label"] == "TD9" and td["direction"] == "sell" and td["countdown"] == 9
    td_none = td_state_view({})
    assert td_none["label"] == "—" and td_none["countdown"] == 0
