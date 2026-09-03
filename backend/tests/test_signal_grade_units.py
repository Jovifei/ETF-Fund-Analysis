from __future__ import annotations

from app.services.signal_grade_service import quote_percent_points_to_ratio


def test_quote_percentage_points_are_normalized_to_decimal_returns():
    assert quote_percent_points_to_ratio(1.2) == 0.012
    assert quote_percent_points_to_ratio(-0.35) == -0.0035
    assert quote_percent_points_to_ratio(0) == 0.0
    assert quote_percent_points_to_ratio(None) is None
