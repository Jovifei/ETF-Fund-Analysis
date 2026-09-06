from __future__ import annotations

import time

from app.core.config import Settings


def test_data_source_readiness_is_sanitized_and_requires_tushare_prerequisites(monkeypatch):
    from app.providers import readiness

    monkeypatch.setattr(readiness, "module_available", lambda name: name == "akshare")
    token = "unit-token-1234567890"
    payload = readiness.source_readiness(
        Settings(market_provider="public_composite", tushare_token=token)
    )

    assert token not in str(payload)
    assert payload["effective_provider"] == "public_composite"
    assert payload["can_initialize_daily_bars"] is True
    by_id = {row["id"]: row for row in payload["sources"]}
    assert by_id["akshare"]["status"] == "ready_unprobed"
    assert by_id["tushare"]["status"] == "missing_dependency"
    assert by_id["ftshare"]["status"] == "disabled"
    assert payload["realtime_quote_status"] == "not_qualified"


def test_data_source_readiness_marks_tushare_token_missing_without_reading_a_token(monkeypatch):
    from app.providers import readiness

    monkeypatch.setattr(readiness, "module_available", lambda name: name == "tushare")
    payload = readiness.source_readiness(Settings(market_provider="tushare"))

    source = payload["sources"][0]
    assert source["id"] == "tushare"
    assert source["status"] == "missing_token"
    assert payload["can_initialize_daily_bars"] is False


def test_workspace_data_source_endpoint_is_non_network_and_never_returns_a_token(bootstrapped):
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        response = client.get("/api/workspace/data-sources")
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "demo_only"
    assert body["can_initialize_daily_bars"] is False
    assert body["tushare_token_set"] is False


def test_workspace_catalog_sync_audits_a_successful_catalog(db_session):
    from app.models import ProviderAudit
    from app.providers.types import InstrumentRecord
    from app.workspace.worker import sync_catalog

    class Provider:
        name = "mock"

        def list_instruments(self):
            return [
                InstrumentRecord(
                    ts_code="599999.SH",
                    symbol="599999",
                    name="测试目录ETF",
                    kind="ETF",
                    exchange="SH",
                    enabled=False,
                )
            ]

    outcome = sync_catalog(
        db_session,
        Provider(),
        run_id="workspace-catalog-test",
        enable_codes=["599999.SH"],
    )

    assert outcome["enabled_requested"] == 1
    audit = db_session.query(ProviderAudit).filter(ProviderAudit.run_id == "workspace-catalog-test").one()
    assert audit.operation == "list_etf_catalog"
    assert audit.status == "ok"


def test_provider_qualification_cli_binds_requested_provider_instead_of_only_relabeling_output():
    from scripts.qualify_market_data import qualification_settings

    configured = Settings(market_provider="mock", allow_mock_fallback=True)
    effective = qualification_settings(configured, "akshare")

    assert effective.market_provider == "akshare"
    assert effective.allow_mock_fallback is False


def test_provider_qualification_timeout_does_not_wait_for_an_unfinished_call():
    from scripts.qualify_market_data import _call_with_timeout

    started = time.perf_counter()
    result, error = _call_with_timeout(lambda: time.sleep(0.25), 0.01)

    assert result is None
    assert isinstance(error, TimeoutError)
    assert time.perf_counter() - started < 0.15
