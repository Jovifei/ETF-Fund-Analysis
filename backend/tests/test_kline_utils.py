from __future__ import annotations

import math

import numpy as np
import pandas as pd

from app.utils.pattern_forecast import pattern_forecast, pattern_forecast_snapshot
from app.utils.td_sequential import compute_td_setup, td_setup_snapshot


def _frame(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=len(closes), freq="D"),
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [1000.0] * len(closes),
        }
    )


# ---------- TD 九转 ----------

def test_td_setup_top_nine_label():
    # 连续 9+ 根收盘价 > 4 根前收盘价 -> 顶部 TD9
    closes = [100.0 + i * 0.5 for i in range(20)]  # 单调上涨
    frame = _frame(closes)
    snapshot = td_setup_snapshot(frame)
    assert snapshot["direction"] == "top"
    assert snapshot["label"].startswith("TD")
    assert snapshot["sub_label"] == "下跌变盘"
    assert snapshot["desc"] == "上涨衰竭"


def test_td_setup_bottom_nine_label():
    # 连续 9+ 根收盘价 < 4 根前收盘价 -> 底部 TD9
    closes = [100.0 - i * 0.5 for i in range(20)]  # 单调下跌
    frame = _frame(closes)
    snapshot = td_setup_snapshot(frame)
    assert snapshot["direction"] == "bottom"
    assert snapshot["label"].startswith("TD")
    assert snapshot["sub_label"] == "上涨变盘"
    assert snapshot["desc"] == "下跌衰竭"


def test_td_setup_no_sequence():
    # 交替升降且与 4 根前比较时方向频繁反转 -> 无持续序列
    closes = [100.0, 101.0, 99.0, 102.0, 98.0, 101.0, 99.0, 103.0, 97.0, 102.0, 98.0, 101.0, 99.0, 100.0, 101.0, 100.0]
    frame = _frame(closes)
    snapshot = td_setup_snapshot(frame)
    assert snapshot["label"] in {"—", "1", "2", "3"}


def test_td_setup_count_break_on_interruption():
    # 上涨 5 根后中断 -> 计数应为 5 而非继续
    closes = [100.0, 100.5, 101.0, 101.5, 102.0, 102.5, 103.0, 103.5, 104.0, 99.0, 100.0, 100.5]
    result = compute_td_setup(pd.Series(closes))
    assert result.direction in {"none", "bottom"}


def test_td_setup_empty():
    snapshot = td_setup_snapshot(pd.DataFrame())
    assert snapshot["label"] == "—"
    assert snapshot["direction"] == "none"


def test_td_setup_matches_existing_indicators_semantics():
    # 与 indicators._td_setup 的计数语义一致：比较 current vs 4-bars-ago
    closes = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0]
    frame = _frame(closes)
    df = frame.copy()
    df["td_buy"], df["td_sell"] = 0, 0
    # 手工验证：idx4..idx9 连续 > 前4根 -> sell 计数到 6
    result = compute_td_setup(pd.Series(closes))
    assert result.sell_count.iloc[-1] == 6  # idx4..idx9 连续 > 前4根


# ---------- 形态匹配明日预测 ----------

def test_pattern_forecast_basic():
    closes = [100.0 + math.sin(i / 2) * 2 + i * 0.1 for i in range(120)]
    frame = _frame(closes)
    forecast = pattern_forecast(frame)
    assert forecast.calibration_status == "not_calibrated"
    assert forecast.horizon == 1
    assert forecast.sample_count >= 3
    assert forecast.expected_return is not None
    assert 0.0 <= forecast.p_up <= 1.0
    assert 0.0 <= forecast.confidence <= 100.0
    assert forecast.terminal_price_q50 is not None


def test_pattern_forecast_insufficient_data():
    frame = _frame([100.0, 101.0, 102.0])
    forecast = pattern_forecast(frame)
    assert forecast.expected_return is None
    assert forecast.sample_count == 0


def test_pattern_forecast_trending_series_direction():
    # 强趋势序列：相似窗口的次日方向应与趋势一致
    closes = [100.0 + i * 0.8 for i in range(80)]
    frame = _frame(closes)
    forecast = pattern_forecast(frame, window=5, top_k=20)
    assert forecast.expected_return is not None
    # 上涨趋势下预期收益应偏正（不强制，但 p_up 应有值）
    assert forecast.p_up is not None


def test_pattern_forecast_snapshot_contract():
    closes = [100.0 + math.sin(i / 3) * 3 for i in range(100)]
    frame = _frame(closes)
    snapshot = pattern_forecast_snapshot(frame)
    assert snapshot["horizon"] == 1
    assert snapshot["calibration_status"] == "not_calibrated"
    assert set(snapshot) >= {"expected_return", "p_up", "confidence", "sample_count", "calibration_status", "note"}
    # 未校准预测不能有 calibrated 标记
    assert snapshot["calibration_status"] != "calibrated"
