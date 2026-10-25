from __future__ import annotations

import json
from pathlib import Path
import pytest


def test_shadow_signal_grade_comparison_output_validity():
    worktree_root = Path(__file__).resolve().parents[2]
    json_path = worktree_root / "research" / "calc_decision" / "out" / "shadow_comparison_signal_grade.json"

    assert json_path.exists(), f"Missing shadow comparison output: {json_path}"
    data = json.loads(json_path.read_text(encoding="utf-8"))

    assert data["contract"] == "A3.3-shadow-signal-grade-comparison-v1"
    assert data["total_evaluated_bars"] > 30000

    # Verify five grades present
    grades = set(data["grade_counts"].keys())
    assert {"可加仓", "可入场", "可试探", "观望", "减仓"}.issubset(grades)

    # Verify divergence analysis
    div = data["divergence_and_false_alarm_analysis"]
    approved = div["sg_bullish_c1_approved"]
    rejected = div["sg_bullish_c1_filtered_out"]

    assert approved["count"] > 1000
    assert rejected["count"] > 5000
    # C1 approved signals should have higher win rate than rejected ones
    assert approved["win_rate_7"] > rejected["win_rate_7"]
    assert div["sg_bullish_c1_filtered_out"]["filtering_alpha"] >= 0.0
