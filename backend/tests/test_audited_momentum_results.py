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

    # Check 3: Report contains audit declarations
    report_text = report_md.read_text(encoding="utf-8")
    assert "前瞻多日收益窗口彻底纠偏" in report_text
    assert "真实扣费与次日开盘成交" in report_text
    assert "双动量（C1）与截面动量（C0）严格公平对照" in report_text
    assert "research_only=true" in report_text
