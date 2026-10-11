"""Research-only RS + vol gate stub tests."""
from __future__ import annotations

from app.utils.sector_rs_vol_gate import annotate_theme_observation, relative_strength_20d, simple_vol_gate


def test_relative_strength_ranks_without_actionable() -> None:
    payload = relative_strength_20d(0.05, [0.01, 0.02, 0.04, 0.06])
    assert payload["actionable"] is False
    assert payload["research_only"] is True
    assert payload["rank"] == 2
    assert payload["peer_count"] == 4


def test_vol_gate_unavailable_on_short_sample() -> None:
    payload = simple_vol_gate([0.01, 0.02])
    assert payload["gate"] == "unavailable"
    assert payload["actionable"] is False


def test_vol_gate_flags_elevated_sample() -> None:
    series = [0.08, -0.07, 0.09, -0.08, 0.06, -0.05]
    payload = simple_vol_gate(series)
    assert payload["high_vol"] is True
    assert payload["actionable"] is False


def test_annotate_keeps_theme_grade_untouched() -> None:
    theme = {"theme_l1": "tech", "mean_return_5d": 0.02, "member_returns": [0.01, 0.02, 0.0, -0.01, 0.03]}
    out = annotate_theme_observation(theme, peer_returns_20d=[0.0, 0.01, 0.03])
    assert out.get("grade") == theme.get("grade")
    assert out["actionable"] is False
    assert out["rs_20d"]["research_only"] is True
