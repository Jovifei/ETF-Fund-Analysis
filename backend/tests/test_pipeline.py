from __future__ import annotations

from sqlalchemy import func, select

from app.db.session import session_scope
from app.models import DailyBar, ForecastSnapshot, IndicatorSnapshot, Instrument, SignalSnapshot


def test_mock_pipeline_builds_research_layers(bootstrapped):
    assert bootstrapped["steps"]["refresh_bars"]["inserted"] > 1000
    assert bootstrapped["steps"]["refresh_forecasts"]["created"] >= 20
    with session_scope() as db:
        instruments = db.scalar(select(func.count()).select_from(Instrument))
        bars = db.scalar(select(func.count()).select_from(DailyBar))
        forecasts = db.scalar(select(func.count()).select_from(ForecastSnapshot))
        signals = db.scalars(select(SignalSnapshot).order_by(SignalSnapshot.as_of_time.desc())).all()
        indicators = db.scalars(select(IndicatorSnapshot).order_by(IndicatorSnapshot.as_of_date.desc())).all()
    assert instruments >= 9
    assert bars >= 2000
    assert forecasts >= 20
    assert signals
    assert indicators
    latest_values = indicators[0].values_json
    assert "rps20" in latest_values and "rps60" in latest_values and "rps120" in latest_values
    assert "strategy_family_scores" in latest_values
    assert "strategy_signals" in latest_values
    assert "chip_peak_price" in latest_values
    assert all(not item.is_actionable for item in signals)
    assert all(item.state not in {"加仓", "小幅加仓", "减仓"} for item in signals)
