from __future__ import annotations

from sqlalchemy import func, select

from app.db.session import session_scope
from app.models import DailyBar, ForecastSnapshot, Instrument, SignalSnapshot


def test_mock_pipeline_builds_research_layers(bootstrapped):
    assert bootstrapped["steps"]["refresh_bars"]["inserted"] > 1000
    assert bootstrapped["steps"]["refresh_forecasts"]["created"] >= 20
    with session_scope() as db:
        instruments = db.scalar(select(func.count()).select_from(Instrument))
        bars = db.scalar(select(func.count()).select_from(DailyBar))
        forecasts = db.scalar(select(func.count()).select_from(ForecastSnapshot))
        signals = db.scalars(select(SignalSnapshot).order_by(SignalSnapshot.as_of_time.desc())).all()
    assert instruments >= 9
    assert bars >= 2000
    assert forecasts >= 20
    assert signals
    # Mock data is marked degraded; no signal may become execution-grade.
    assert all(not item.is_actionable for item in signals)
    # Without holdings, the state machine cannot emit add/reduce language.
    assert all(item.state not in {"加仓", "小幅加仓", "减仓"} for item in signals)
