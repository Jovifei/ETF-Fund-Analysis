from __future__ import annotations

from app.core.config import Settings
from app.db.session import session_scope
from app.models import DailyBar, ForecastSnapshot, IndicatorSnapshot, Instrument, SignalSnapshot
from sqlalchemy import func, select


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
    # Mock data is marked degraded; no signal may become execution-grade.
    assert all(not item.is_actionable for item in signals)
    # Without holdings, the state machine cannot emit add/reduce language.
    assert all(item.state not in {"加仓", "小幅加仓", "减仓"} for item in signals)


def test_bootstrap_includes_market_context_step_with_truthful_default_unavailability(bootstrapped):
    context = bootstrapped["steps"]["refresh_market_context"]
    assert context["status"] == "succeeded"
    assert context["configured"] == 6
    assert context["eligible"] == 0
    assert context["observed"] == 0
    assert context["missing"] == 0
    assert context["provider_calls"] == 0
    assert context["mock"] == 0
    assert context["degraded"] == 0
    assert context["unsupported"] == 0


def test_v050_runtime_wiring_remains_selected_for_tasks():
    from app.services.backtest_v05_service import RotationBacktestV05Service
    from app.services.signal_v05_service import SignalV05Service
    from app.services.task_service import TaskService

    service = TaskService(Settings(_env_file=None))
    assert isinstance(service.signals, SignalV05Service)
    assert isinstance(service.backtest, RotationBacktestV05Service)
    assert "backtest_ablation" in service.task_names
