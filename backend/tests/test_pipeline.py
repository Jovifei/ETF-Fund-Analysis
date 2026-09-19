from __future__ import annotations

from types import SimpleNamespace

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


def test_bootstrap_includes_market_context_step_generating_mock_observations(bootstrapped):
    context = bootstrapped["steps"]["refresh_market_context"]
    # Collection returned all mock records, but degraded evidence is not full success.
    assert context["status"] == "partial"
    assert context["coverage_complete"] is False
    # 默认 registry 含 9 张卡片，其中 7 张启用（A股/美股大盘指数 + 半导体代理）；
    # mock 环境下会为启用卡片生成 degraded mock 观测（demo 隔离，非真实数据）。
    assert context["configured"] == 9
    assert context["eligible"] == 7
    assert context["observed"] == 7
    assert context["missing"] == 0
    assert context["provider_calls"] == 1
    assert context["mock"] == 7
    assert context["degraded"] == 7
    assert context["unsupported"] == 0


def test_v050_runtime_wiring_remains_selected_for_tasks():
    from app.services.backtest_v05_service import RotationBacktestV05Service
    from app.services.signal_v05_service import SignalV05Service
    from app.services.task_service import TaskService

    service = TaskService(Settings(_env_file=None))
    assert isinstance(service.signals, SignalV05Service)
    assert isinstance(service.backtest, RotationBacktestV05Service)
    assert "backtest_ablation" in service.task_names


def test_full_pipeline_refreshes_sector_context_before_publishing_board(monkeypatch, db_session):
    from app.services.task_service import TaskService

    calls = []
    service = TaskService(Settings(_env_file=None, market_provider="mock"))
    succeeded = lambda name: lambda *args, **kwargs: calls.append(name) or {"status": "succeeded"}
    monkeypatch.setattr(service.market, "sync_instruments", succeeded("sync_instruments"))
    monkeypatch.setattr(service, "_refresh_market_context", succeeded("refresh_market_context"))
    monkeypatch.setattr(service.market, "refresh_daily_bars", succeeded("refresh_bars"))
    monkeypatch.setattr(service.indicators, "refresh_all", succeeded("refresh_indicators"))
    monkeypatch.setattr(service.forecasts, "refresh_all", succeeded("refresh_forecasts"))
    monkeypatch.setattr(service.market, "refresh_quotes", succeeded("refresh_quotes"))
    monkeypatch.setattr(service.news, "refresh", succeeded("refresh_news"))
    monkeypatch.setattr(service.signals, "refresh_all", succeeded("refresh_signals"))
    monkeypatch.setattr(service.market, "refresh_sector_snapshots", succeeded("refresh_sector_snapshots"))
    monkeypatch.setattr(
        service.decision_board,
        "refresh",
        lambda *args, **kwargs: calls.append("refresh_decision_board")
        or SimpleNamespace(snapshot=SimpleNamespace(snapshot_id="pipeline-order")),
    )
    monkeypatch.setattr(service.reports, "generate", succeeded("generate_report"))
    try:
        service.run(db_session, "full_pipeline", report=False)
    finally:
        service.close()

    assert calls.index("refresh_sector_snapshots") < calls.index("refresh_decision_board")
