"""Research-only RS + vol gate stub tests."""
from __future__ import annotations

import pytest

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


def test_missing_20d_does_not_borrow_5d() -> None:
    out = annotate_theme_observation({"mean_return_5d": 0.2}, peer_returns_20d=[0.1])
    assert out["rs_20d"]["return_20d"] is None
    assert out["rs_20d"]["rank"] is None


@pytest.mark.parametrize("field", ["member_returns", "returns_sample", "daily_returns"])
def test_unknown_axis_does_not_become_realized_volatility(field: str) -> None:
    out = annotate_theme_observation({field: [0.1, -0.1, 0.1, -0.1, 0.1]})
    assert out["vol_gate"]["gate"] == "unavailable"
    assert out["vol_gate"]["note"] == "daily_time_series_axis_required"


def test_explicit_daily_series_preserves_stdev_math_and_research_boundary() -> None:
    theme = {"grade": "watch", "returns_axis": "daily_time_series",
             "daily_returns": [0.08, -0.07, 0.09, -0.08, 0.06, -0.05]}
    original = dict(theme)
    out = annotate_theme_observation(theme)
    assert out["vol_gate"]["stdev"] == simple_vol_gate(theme["daily_returns"])["stdev"]
    assert out["vol_gate"]["stdev"] == 0.079687
    assert out["vol_gate"]["high_vol"] is True
    assert out["contract_version"] == "sector-rs-vol-research-v2"
    assert out["grade"] == "watch"
    assert out["actionable"] is False
    assert theme == original


def test_unimplemented_percentile_configuration_is_rejected() -> None:
    with pytest.raises(TypeError):
        simple_vol_gate([0.1] * 5, high_vol_percentile=0.8)


def test_explicit_axis_does_not_authorize_member_sample() -> None:
    out = annotate_theme_observation({"returns_axis": "daily_time_series",
                                      "member_returns": [0.1, -0.1, 0.1, -0.1, 0.1]})
    assert out["vol_gate"]["gate"] == "unavailable"


def test_invalid_values_do_not_count_as_daily_observations() -> None:
    out = simple_vol_gate([True, float("nan"), float("inf"), 0.1, -0.1, 0.1, -0.1])
    assert out["gate"] == "unavailable"
    assert "high_vol_percentile_config" not in out
