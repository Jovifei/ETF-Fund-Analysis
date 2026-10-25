from __future__ import annotations

from pathlib import Path
import pandas as pd
import pytest


def test_audited_metrics_csv_and_report_consistency():
    worktree_root = Path(__file__).resolve().parents[2]
    out_csv = worktree_root / "research" / "calc_decision" / "out" / "factor_empirical_metrics_audited_20261024.csv"
    docs_csv = worktree_root / "docs" / "research" / "factor_empirical_metrics_audited_20261024.csv"
    report_md = worktree_root / "docs" / "research" / "ETF_MOMENTUM_VALIDATION_REPORT_20261024.md"

    assert out_csv.exists(), f"Missing {out_csv}"
    assert docs_csv.exists(), f"Missing {docs_csv}"
    assert report_md.exists(), f"Missing {report_md}"

    df = pd.read_csv(docs_csv)
    assert len(df) == 320  # 16 factors * 4 samples * 5 horizons = 320 records

    # Verify required factors exist
    factors = set(df["factor"].unique())
    assert "mom_120_cs" in factors
    assert "tsmom_12m" in factors
    assert "tsmom_voltarget_m2" in factors
    assert "dual_momentum_c1" in factors
    assert "z_mr_20" in factors

    # Check 1: Sharpe consistency for a factor across horizons in same sample
    hold_m120 = df[(df["factor"] == "mom_120_cs") & (df["sample"] == "holdout_2y_longhist")]
    sh_values = hold_m120["net_sharpe_d1"].unique()
    assert len(sh_values) == 1, "Net Sharpe must be unified and fixed across horizons for the same slice!"

    # Check 2: Wilson intervals exist and bound hit_rate
    sub_with_hits = df.dropna(subset=["hit_rate", "hit_rate_wilson_lo", "hit_rate_wilson_hi"])
    for _, row in sub_with_hits.iterrows():
        assert row["hit_rate_wilson_lo"] <= row["hit_rate"] <= row["hit_rate_wilson_hi"]

    # Check 3: Drawdown sanity (B0 is unleveraged, no -173.6% explosion)
    b0_mdd = df[(df["factor"] == "equal_weight_b0") & (df["sample"] == "holdout_2y_longhist")]["net_max_drawdown"].iloc[0]
    assert -0.35 <= b0_mdd <= 0.0, f"B0 drawdown {b0_mdd} must be within normal unleveraged range"

    # Check 4: Report contains audit declarations
    report_text = report_md.read_text(encoding="utf-8")
    assert "等权基准（B0）与资金预算约束" in report_text
    assert "加仓与减仓真实入账" in report_text
    assert "统一日净值与逐笔账本" in report_text
    assert "样本外与统计边界诚实化" in report_text
    assert "research_only=true" in report_text
