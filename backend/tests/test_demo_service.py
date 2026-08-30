from __future__ import annotations

from sqlalchemy import func, select, create_engine
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
import httpx

from app.core.config import Settings
from app.db.base import Base
from app.main import app
from app.models import DailyBar, IndicatorSnapshot, Instrument, ProviderAudit, Holding, TaskRun
from app.providers.mock import MockProvider
from app.services.task_service import TaskService
from app.services.demo_service import DemoService


def test_demo_load_isolated_and_non_actionable(bootstrapped, db_session):
    production_counts = {
        model.__name__: db_session.scalar(select(func.count()).select_from(model))
        for model in (Instrument, DailyBar, IndicatorSnapshot, ProviderAudit, Holding)
    }
    DemoService.reset()
    try:
        payload = DemoService().load()
        assert payload["demo"] is True
        assert payload["is_mock"] is True
        assert payload["research_only"] is True
        assert payload["actionable"] is False
        assert payload["status"] == "ready"
        assert len(payload["instruments"]) >= 9
        assert payload["signal_grade"]["counts"].get("数据异常", 0) == 0
        assert all(row["actionable"] is False for row in payload["instruments"])
        for key in ("market_context", "news", "tasks", "provider_health"):
            assert all(
                item["demo"] is True
                and item["is_mock"] is True
                and item["research_only"] is True
                and item["actionable"] is False
                for item in payload[key]
            )
        assert all(item["demo"] is True for item in payload["signal_grade"]["rows"])
        # Demo calculations need their domain rows, but must not create audit
        # history that looks like a formal task or external-provider activity.
        runtime = DemoService._runtime
        assert runtime is not None
        with runtime.sessions() as demo_db:
            assert demo_db.scalar(select(func.count()).select_from(ProviderAudit)) == 0
            assert demo_db.scalar(select(func.count()).select_from(TaskRun)) == 0
        assert payload["tasks"] == []
        assert payload["provider_health"] == []
        assert all(
            row["bars"] >= 420
            for row in payload.get("demo_quality", {}).get("instruments", [])
        )
        assert {
            model.__name__: db_session.scalar(select(func.count()).select_from(model))
            for model in (Instrument, DailyBar, IndicatorSnapshot, ProviderAudit, Holding)
        } == production_counts
    finally:
        DemoService.reset()


def test_demo_status_before_load_and_after_reset():
    DemoService.reset()
    assert DemoService().bootstrap()["status_label"] == "待初始化"
    DemoService().load()
    reset = DemoService.reset()
    assert reset["status"] == "pending"
    assert DemoService().bootstrap()["status"] == "pending"


def test_demo_hard_disables_network_capable_integrations(monkeypatch):
    settings = Settings(
        _env_file=None,
        app_env="test",
        market_provider="composite",
        analysis_enabled=True,
        analysis_primary_provider="codex_openai_responses",
        analysis_primary_model="adversarial-model",
        analysis_codex_enabled=True,
        openai_api_key="adversarial-key",
    )
    calls = []

    def no_network(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("demo attempted external network access")

    monkeypatch.setattr(httpx.Client, "request", no_network)
    DemoService.reset()
    try:
        payload = DemoService(settings).load()
        assert payload["status"] == "ready"
        assert calls == []
    finally:
        DemoService.reset()


def test_demo_status_origins_are_mutually_exclusive():
    DemoService.reset()
    DemoService().load()
    runtime = DemoService._runtime
    assert runtime is not None
    try:
        with runtime.sessions() as db:
            assert DemoService._classify_status(db, None) == "pending"
            assert DemoService._classify_status(
                db, {"failure_stage": "provider", "steps": {}}
            ) == "provider_unavailable"
            assert DemoService._classify_status(
                db, {"failure_stage": "core", "steps": {}}
            ) == "data_anomaly"
            first = db.scalar(select(Instrument).order_by(Instrument.id).limit(1))
            assert first is not None
            db.query(DailyBar).filter(DailyBar.instrument_id == first.id).delete()
            db.flush()
            assert DemoService._classify_status(db, {"steps": {}}) == "insufficient"
    finally:
        DemoService.reset()


def test_demo_closes_injected_provider_once(monkeypatch):
    import app.services.demo_service as module

    class TrackingProvider(MockProvider):
        closed = 0

        def close(self):
            type(self).closed += 1

    monkeypatch.setattr(module, "MockProvider", TrackingProvider)
    DemoService.reset()
    DemoService().load()
    DemoService.reset()
    DemoService.reset()
    assert TrackingProvider.closed == 1


def test_demo_classifies_injected_provider_and_core_failures(monkeypatch):
    def provider_failure(runtime, db):
        del runtime, db
        return {"status": "failed", "failure_stage": "provider", "steps": {}}

    monkeypatch.setattr(DemoService, "_run_pipeline", staticmethod(provider_failure))
    DemoService.reset()
    try:
        assert DemoService().load()["status"] == "provider_unavailable"
    finally:
        DemoService.reset()

    def core_failure(runtime, db):
        runtime.task_service.run(db, "sync_instruments")
        runtime.task_service.run(db, "refresh_bars", lookback_days=120)
        return {"status": "failed", "failure_stage": "core", "steps": {}}

    monkeypatch.setattr(DemoService, "_run_pipeline", staticmethod(core_failure))
    try:
        assert DemoService().load()["status"] == "data_anomaly"
    finally:
        DemoService.reset()


def test_app_lifespan_disposes_demo_runtime():
    DemoService.reset()
    DemoService().load()
    assert DemoService().bootstrap()["status"] == "ready"
    with TestClient(app):
        assert DemoService().bootstrap()["status"] == "ready"
    assert DemoService().bootstrap()["status"] == "pending"


def test_demo_endpoints_are_private_and_reject_controls(bootstrapped):
    DemoService.reset()
    with TestClient(app) as client:
        response = client.post("/api/demo/load", json={"provider_url": "https://evil.invalid"})
        assert response.status_code == 422
        response = client.post("/api/demo/load")
        assert response.status_code == 200
        assert response.json()["demo"] is True
        assert client.get("/api/demo/bootstrap").json()["actionable"] is False
        assert client.post("/api/demo/reset").json()["status"] == "pending"


def test_refresh_bars_30_calendar_days_skips_and_120_generates_indicators():
    settings = Settings(_env_file=None, app_env="test", market_provider="mock")
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
    )
    Base.metadata.create_all(bind=engine)
    provider = MockProvider(settings)
    service = TaskService(settings, provider=provider)
    try:
        with Session(engine) as db:
            service.run(db, "sync_instruments")
            service.run(db, "refresh_bars", lookback_days=30)
            short = service.run(db, "refresh_indicators")
            assert short["created"] == 0
            service.run(db, "refresh_bars", lookback_days=120)
            long = service.run(db, "refresh_indicators")
            assert long["created"] > 0
    finally:
        service.close()
        engine.dispose()
