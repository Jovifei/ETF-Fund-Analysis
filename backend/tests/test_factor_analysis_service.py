from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.services.factor_analysis_service import factor_metric


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
