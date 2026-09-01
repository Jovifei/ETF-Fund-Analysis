from __future__ import annotations

import json

from app.core.config import Settings
from app.main import app
from app.providers.mock import MockProvider
from app.providers.types import BarRecord
from app.services.runtime_service import RuntimeService
from app.services.task_service import TaskService
from fastapi.testclient import TestClient

FAKE_TOKEN = "unit-ts-1234567890"


def _assert_no_secret(payload: object, secret: str = FAKE_TOKEN) -> None:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=True)
    assert secret not in text
    if isinstance(payload, dict):
        assert "tushare_token" not in payload


def test_settings_public_view_never_returns_token(bootstrapped):
    with TestClient(app) as client:
        response = client.get("/api/settings")
        assert response.status_code == 200
        body = response.json()
        _assert_no_secret(body)
        assert body["market_data_tier"] in {"usable", "complete"}
        assert "tushare_token_set" in body
        assert "active_provider" in body
        assert body["active_provider"] == "mock"


def test_settings_store_token_without_echo_and_empty_does_not_clear(bootstrapped):
    with TestClient(app) as client:
        saved = client.put(
            "/api/settings",
            json={"market_data_tier": "complete", "tushare_token": FAKE_TOKEN},
        )
        assert saved.status_code == 200
        _assert_no_secret(saved.json())
        assert saved.json()["market_data_tier"] == "complete"
        assert saved.json()["tushare_token_set"] is True

        again = client.get("/api/settings")
        assert again.status_code == 200
        _assert_no_secret(again.text)
        assert again.json()["tushare_token_set"] is True

        keep = client.put("/api/settings", json={"tushare_token": "   "})
        assert keep.status_code == 200
        _assert_no_secret(keep.json())
        assert keep.json()["tushare_token_set"] is True

        cleared = client.put("/api/settings", json={"clear_tushare_token": True, "market_data_tier": "usable"})
        assert cleared.status_code == 200
        _assert_no_secret(cleared.json())
        assert cleared.json()["tushare_token_set"] is False
        assert cleared.json()["market_data_tier"] == "usable"


def test_settings_reject_malformed_token_without_echo(bootstrapped):
    bad = "not a valid token!!"
    with TestClient(app) as client:
        response = client.put("/api/settings", json={"tushare_token": bad})
        assert response.status_code == 422
        assert bad not in response.text
        _assert_no_secret(response.text, bad)


def test_market_probe_on_mock_skips_network_and_never_echoes_token(bootstrapped):
    with TestClient(app) as client:
        client.put("/api/settings", json={"market_data_tier": "usable"})
        probed = client.post(
            "/api/settings/market-probe",
            json={"tushare_token": FAKE_TOKEN, "market_data_tier": "complete"},
        )
        assert probed.status_code == 200
        body = probed.json()
        _assert_no_secret(body)
        assert body["skipped"] is True
        assert body["ok"] is False
        assert body["provider"] == "mock"
        assert body["tier"] == "complete"
        assert body["probe_code"] == "510300.SH"
        assert isinstance(body["providers"], list)
        assert body["providers"][0]["provider"] == "mock"
        assert body["providers"][0]["operation"] == "probe_market"
        assert set(("provider", "operation", "ok", "status", "records", "latency", "failure_class", "qualification")) <= set(body["providers"][0])
        client.put("/api/settings", json={"clear_tushare_token": True, "market_data_tier": "usable"})


def test_settings_exposes_ftshare_safe_state_without_credentials(bootstrapped):
    with TestClient(app) as client:
        response = client.get("/api/settings")
        assert response.status_code == 200
        body = response.json()
        assert body["ftshare_enabled"] is False
        assert body["ftshare_qualification"] in {"unqualified", "unverified", "qualified", "rejected"}
        assert body["ftshare_ready"] is False
        assert body["ftshare_last_probe"] is None or isinstance(body["ftshare_last_probe"], dict)
        assert "ftshare_base_url" not in body
        assert "https://market.ft.tech" not in json.dumps(body, ensure_ascii=True)


def test_resolve_settings_keeps_mock_and_uses_qualified_ftshare_public_chain(db_session):
    mock_settings = Settings(_env_file=None, market_provider="mock")
    mock_runtime = RuntimeService(mock_settings)
    mock_runtime.update(db_session, {"market_data_tier": "complete", "tushare_token": FAKE_TOKEN})
    resolved_mock = mock_runtime.resolve_settings(db_session)
    assert resolved_mock.market_provider == "mock"

    live = Settings(
        _env_file=None,
        market_provider="akshare",
        tushare_token="",
        ftshare_enabled=True,
        ftshare_qualification="qualified",
    )
    runtime = RuntimeService(live)
    runtime.update(db_session, {"clear_tushare_token": True, "market_data_tier": "usable"})
    usable = runtime.resolve_settings(db_session)
    assert usable.market_provider == "public_composite"

    runtime.update(db_session, {"market_data_tier": "complete"})
    complete_without_token = runtime.resolve_settings(db_session)
    assert complete_without_token.market_provider == "public_composite"

    runtime.update(db_session, {"market_data_tier": "complete", "tushare_token": FAKE_TOKEN})
    complete = runtime.resolve_settings(db_session)
    assert complete.market_provider == "composite"
    assert complete.tushare_token == FAKE_TOKEN

    runtime.update(db_session, {"clear_tushare_token": True, "market_data_tier": "usable"})
    fallback = runtime.resolve_settings(db_session)
    assert fallback.market_provider == "public_composite"

    unqualified = RuntimeService(
        Settings(_env_file=None, market_provider="akshare", ftshare_enabled=True, ftshare_qualification="unverified")
    )
    unqualified.update(db_session, {"market_data_tier": "usable"})
    assert unqualified.resolve_settings(db_session).market_provider == "akshare"


def test_market_probe_returns_bounded_provider_matrix_without_raw_errors(db_session, monkeypatch):
    settings = Settings(_env_file=None, market_provider="akshare", ftshare_enabled=False)
    runtime = RuntimeService(settings)

    class FakeProvider:
        def __init__(self, provider_settings):
            self.name = provider_settings.market_provider

        def fetch_daily_bars(self, code, start, end):
            return [BarRecord(ts_code=code, trade_date=end, open=1, high=1, low=1, close=1, volume=1, amount=1, source=self.name)]

        def close(self):
            return None

    monkeypatch.setattr("app.services.runtime_service.create_provider", FakeProvider)
    result = runtime.probe_market(db_session, tier_override="complete")
    assert result["ok"] is True
    assert [row["provider"] for row in result["providers"]] == ["tushare", "akshare", "ftshare"]
    assert result["providers"][0]["status"] == "skipped"
    assert result["providers"][0]["failure_class"] == "credentials_missing"
    assert result["providers"][2]["status"] == "skipped"
    for row in result["providers"]:
        assert set(("provider", "operation", "ok", "status", "records", "latency", "failure_class", "qualification")) == set(row)


def test_usable_market_probe_keeps_akshare_before_tushare_when_token_exists(db_session, monkeypatch):
    settings = Settings(_env_file=None, market_provider="akshare", tushare_token=FAKE_TOKEN, ftshare_enabled=False)
    runtime = RuntimeService(settings)

    class FakeProvider:
        def __init__(self, provider_settings):
            self.name = provider_settings.market_provider

        def fetch_daily_bars(self, code, start, end):
            return [BarRecord(ts_code=code, trade_date=end, open=1, high=1, low=1, close=1, volume=1, amount=1, source=self.name)]

        def close(self):
            return None

    monkeypatch.setattr("app.services.runtime_service.create_provider", FakeProvider)
    result = runtime.probe_market(db_session, tier_override="usable")

    assert [row["provider"] for row in result["providers"]] == ["akshare", "tushare", "ftshare"]
    assert result["providers"][0]["status"] == "ok"
    assert result["providers"][1]["status"] == "ok"
    assert result["providers"][2]["status"] == "skipped"


def test_market_probe_rejects_arbitrary_controls(bootstrapped):
    with TestClient(app) as client:
        response = client.post("/api/settings/market-probe", json={"provider_url": "https://evil.invalid"})
        assert response.status_code == 422


def test_task_service_rebinds_non_mock_provider(db_session, monkeypatch):
    live = Settings(_env_file=None, market_provider="akshare", tushare_token="")
    RuntimeService(live).update(db_session, {"market_data_tier": "complete", "tushare_token": FAKE_TOKEN})
    captured: dict[str, str] = {}

    class FakeProvider:
        name = "composite"

    def fake_create(resolved):
        captured["provider"] = resolved.market_provider
        captured["token"] = resolved.tushare_token
        return FakeProvider()

    monkeypatch.setattr("app.services.task_service.create_provider", fake_create)
    service = TaskService(live, provider=MockProvider(Settings(_env_file=None, market_provider="mock")))
    service.settings = live
    service.runtime = RuntimeService(live)
    service._bind_runtime_provider(db_session)
    assert captured["provider"] == "composite"
    assert captured["token"] == FAKE_TOKEN
    RuntimeService(live).update(db_session, {"clear_tushare_token": True, "market_data_tier": "usable"})


def test_usable_runtime_with_stored_token_binds_public_composite(db_session, monkeypatch):
    live = Settings(_env_file=None, market_provider="akshare", tushare_token="")
    RuntimeService(live).update(db_session, {"market_data_tier": "usable", "tushare_token": FAKE_TOKEN})
    captured: dict[str, str] = {}

    class FakeProvider:
        name = "public_composite"

    def fake_create(resolved):
        captured["provider"] = resolved.market_provider
        captured["token"] = resolved.tushare_token
        return FakeProvider()

    monkeypatch.setattr("app.services.task_service.create_provider", fake_create)
    service = TaskService(live, provider=MockProvider(Settings(_env_file=None, market_provider="mock")))
    service.settings = live
    service.runtime = RuntimeService(live)
    service._bind_runtime_provider(db_session)

    assert captured == {"provider": "public_composite", "token": FAKE_TOKEN}
    RuntimeService(live).update(db_session, {"clear_tushare_token": True, "market_data_tier": "usable"})


def test_settings_public_view_reports_qualified_ftshare_public_chain(db_session):
    settings = Settings(
        _env_file=None,
        market_provider="akshare",
        ftshare_enabled=True,
        ftshare_qualification="qualified",
    )
    runtime = RuntimeService(settings)
    runtime.update(db_session, {"market_data_tier": "usable"})
    assert runtime.get_all(db_session)["active_provider"] == "public_composite"


def test_market_settings_ui_contract():
    from pathlib import Path

    static_root = Path(__file__).parents[1] / "app" / "static"
    index = (static_root / "index.html").read_text(encoding="utf-8")
    script = (static_root / "app.js").read_text(encoding="utf-8")
    assert 'id="marketSourceForm"' in index
    assert 'id="tushareTokenInput"' in index
    assert 'type="password"' in index
    assert "更真实更完整" in index
    assert "先能用" in index
    assert "/api/settings/market-probe" in script
    assert "applyMarketSettings" in script
    assert "tushare_token" in script
    assert "Number(v)" in script
    assert "demoLoadButton" in index
    assert "demoExitButton" in index
    assert "DEMO" in script
    assert "providers" in script
    assert "blockFormalMutation" in script
    for marker in ("saveHolding", "deleteHolding", "uploadPortfolioImport", "submitBoardFund", "downloadReport", "saveMarketSource", "clearStoredTushareToken", "saveCoefficient"):
        assert marker in script
    assert 'data.demo' in script or 'state.demoMode' in script
    assert 'function blockFormalMutation' in script
    assert "if (data?.demo === true) return 'DEMO'" in script
    assert "['ok', 'fallback_used'].includes(item?.status)" in script
    assert '不访问外网、不写生产数据库' in index
    assert "'不可用'" in script
    assert "return 'unavailable'" in script
    assert "await loadSettings()" in script
    for marker in ("modeGeneration", "modeTransition", "beginModeTransition", "endModeTransition", "modeRequestCurrent", "demoBootstrapController", "abortImportRequests"):
        assert marker in script
    assert "if (state.modeTransition) return null" in script
    assert "escapeHtml(sector.rank)" in script
    assert "escapeHtml(sector.member_count)" in script
