from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.services.factor_analysis_service import (
    DEFAULT_FACTORS,
    OSS_RESEARCH_FACTORS,
    add_oss_research_factor_diagnostics,
    factor_metric,
)
from app.utils.feature_store import HORIZON_FEATURES


def test_factor_metric_reports_rank_ic_spread_and_turnover():
    rows = []
    start = date(2025, 1, 1)
    codes = [f"51{index:04d}.SH" for index in range(8)]
    for day in range(30):
        for index, code in enumerate(codes):
            factor = index / 7 + day * 0.001
            rows.append(
                {
                    "trade_date": start + timedelta(days=day),
                    "ts_code": code,
                    "demo_factor": factor,
                    "forward_return_5": factor * 0.02 + np.sin(day) * 0.0001,
                }
            )
    metric = factor_metric(pd.DataFrame(rows), "demo_factor", 5)
    assert metric.coverage == 1.0
    assert metric.observation_dates == 30
    assert metric.rank_ic_mean is not None and metric.rank_ic_mean > 0.99
    assert metric.icir is None or metric.icir > 1
    assert metric.top_bottom_spread is not None and metric.top_bottom_spread > 0
    assert metric.top_quantile_turnover is not None


def _diagnostic_panel(days: int = 100) -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=days, freq="B").date
    x = np.arange(days, dtype=float)
    benchmark_return = 0.001 + 0.006 * np.sin(x / 5.0) + 0.002 * np.cos(x / 11.0)
    satellite_return = 1.5 * benchmark_return + 0.0008 * np.sin(x / 3.0)
    rows = []
    for code, returns, base, volume_base in (
        ("510300.SH", benchmark_return, 4.0, 1_000_000.0),
        ("159915.SZ", satellite_return, 2.0, 800_000.0),
    ):
        close = base * np.cumprod(1.0 + returns)
        volume = volume_base * (1.0 + 0.15 * np.sin(x / 7.0) + 0.03 * np.cos(x / 2.0))
        for i, day in enumerate(dates):
            rows.append(
                {
                    "trade_date": day,
                    "ts_code": code,
                    "close": float(close[i]),
                    "volume": float(volume[i]),
                    "return_1d": float(returns[i]),
                }
            )
    return pd.DataFrame(rows)


def test_oss_research_factors_are_diagnostic_only_not_production_features() -> None:
    assert set(OSS_RESEARCH_FACTORS) <= set(DEFAULT_FACTORS)
    production = {name for columns in HORIZON_FEATURES.values() for name in columns}
    assert not (set(OSS_RESEARCH_FACTORS) & production)


def test_oss_research_factor_diagnostics_are_point_in_time() -> None:
    panel = _diagnostic_panel()
    baseline = add_oss_research_factor_diagnostics(panel, "510300.SH")
    anchor = panel["trade_date"].sort_values().unique()[75]
    columns = [
        "linear_slope_20",
        "trend_r2_20",
        "trend_residual_20",
        "time_since_high_20",
        "time_since_low_20",
        "up_day_fraction_20",
        "down_day_fraction_20",
        "return_volume_corr_20",
        "benchmark_beta_60",
        "benchmark_corr_60",
    ]
    before = (
        baseline.loc[
            (baseline["ts_code"] == "159915.SZ") & (baseline["trade_date"] == anchor),
            columns,
        ]
        .iloc[0]
        .astype(float)
    )

    shocked = panel.copy()
    future = shocked["trade_date"] > anchor
    shocked.loc[future & (shocked["ts_code"] == "159915.SZ"), "close"] *= 5.0
    shocked.loc[future & (shocked["ts_code"] == "159915.SZ"), "volume"] *= 20.0
    shocked.loc[future & (shocked["ts_code"] == "159915.SZ"), "return_1d"] = -0.25
    shocked.loc[future & (shocked["ts_code"] == "510300.SH"), "return_1d"] = 0.25
    after_panel = add_oss_research_factor_diagnostics(shocked, "510300.SH")
    after = (
        after_panel.loc[
            (after_panel["ts_code"] == "159915.SZ") & (after_panel["trade_date"] == anchor),
            columns,
        ]
        .iloc[0]
        .astype(float)
    )

    np.testing.assert_allclose(before.to_numpy(), after.to_numpy(), equal_nan=True, atol=1e-12, rtol=0)


def test_rolling_benchmark_beta_and_correlation_have_expected_direction() -> None:
    result = add_oss_research_factor_diagnostics(_diagnostic_panel(), "510300.SH")
    satellite = result.loc[result["ts_code"] == "159915.SZ"].sort_values("trade_date").iloc[-1]
    benchmark = result.loc[result["ts_code"] == "510300.SH"].sort_values("trade_date").iloc[-1]

    assert 1.35 < float(satellite["benchmark_beta_60"]) < 1.65
    assert float(satellite["benchmark_corr_60"]) > 0.98
    assert 0.95 < float(benchmark["benchmark_beta_60"]) < 1.05
    assert float(benchmark["benchmark_corr_60"]) > 0.999
    assert np.isfinite(float(satellite["trend_r2_20"]))
    assert 0 <= float(satellite["up_day_fraction_20"]) <= 1
    assert 0 <= float(satellite["down_day_fraction_20"]) <= 1
