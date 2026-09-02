from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.core.config import get_settings
from app.db.session import session_scope
from app.main import app
from app.models import ForecastSnapshot, MarketContextRegistry, MarketContextSnapshot
from app.services.report_service import ReportService
from fastapi.testclient import TestClient
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select


def test_dashboard_api_and_static_assets(bootstrapped):
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        dashboard = client.get("/api/bootstrap")
        assert dashboard.status_code == 200
        payload = dashboard.json()
        assert payload["summary"]["instrument_count"] >= 9
        assert payload["instruments"]
        assert payload["instruments"][0]["quote"]["is_mock"] is True
        assert len(payload["market_context"]) == 9
        assert [row["display_order"] for row in payload["market_context"]] == list(range(1, 10))
        context = client.get("/api/market-context")
        assert context.status_code == 200
        assert context.json()["latest_view"] == payload["market_context"]
        bars = client.get("/api/instruments/510300.SH/bars?limit=25")
        assert bars.status_code == 200 and len(bars.json()) == 25
        index = client.get("/")
        assert index.status_code == 200 and "ETF / LOF 决策台" in index.text
        script = client.get("/assets/app.js")
        assert script.status_code == 200 and "connectEvents" in script.text
        reports = client.get("/api/reports")
        assert reports.status_code == 200 and reports.json()
        latest = reports.json()[0]
        report = client.get(latest["url"])
        assert report.status_code == 200
        assert report.headers["content-type"].startswith(("text/html", "application/json"))


def test_d1_static_dashboard_contract_is_code_first_and_provenance_aware():
    static_root = Path(__file__).parents[1] / "app" / "static"
    index = (static_root / "index.html").read_text(encoding="utf-8")
    script = (static_root / "app.js").read_text(encoding="utf-8")
    css = (static_root / "app.css").read_text(encoding="utf-8")
    report = (Path(__file__).parents[1] / "app" / "templates" / "report.html.j2").read_text(encoding="utf-8")

    for marker in (
        'id="marketContextSection"',
        "中国行业/板块广度与轮动",
        "S&P 500",
        "Nasdaq Composite",
        "Nasdaq-100",
        "中国半导体可交易 ETF 代理",
        "韩国半导体可交易 ETF 代理",
    ):
        assert marker in index or marker in script
    assert "function displayIdentity" in script
    assert "displayIdentity(row.ts_code, row.name)" in script
    assert "displayIdentity(h.ts_code, h.name)" in script
    assert "today_pct_change" in script
    assert "FORECAST · 非实际结果" in script
    for marker in (
        "forecast-surface",
        "observed-surface",
        "sample_count",
        "calibration_status",
        "model_version",
        "data_cutoff",
        "generated_at",
        "prefers-reduced-motion",
    ):
        assert marker in script or marker in css
    assert "displayIdentity(row.ts_code, row.name)" in report
    assert "FORECAST · 非实际结果" in report
    for marker in ("source_timestamp", "fetched_at", "freshness", "q10", "q50", "q90"):
        assert marker in report
    instrument_fragment = script[script.index("function instrumentRow"):script.index("function renderInstruments")]
    assert instrument_fragment.index("quote-change") < instrument_fragment.index("quote-price")
    assert "escapeHtml" in script


def test_d1_static_accessibility_fallback_sse_and_xss_contract():
    static_root = Path(__file__).parents[1] / "app" / "static"
    index = (static_root / "index.html").read_text(encoding="utf-8")
    script = (static_root / "app.js").read_text(encoding="utf-8")
    css = (static_root / "app.css").read_text(encoding="utf-8")

    for context_id in (
        "china-sector-breadth", "us-sp500", "us-nasdaq-composite",
        "us-nasdaq-100", "china-semiconductor-etf", "korea-semiconductor-etf",
    ):
        assert f'context_id: "{context_id}"' in script
    assert "DEFAULT_MARKET_CONTEXT" in script
    assert "function mergeMarketContext" in script
    assert "standardIds" in script
    assert "market_context.updated" in script
    assert 'role="dialog"' in index and 'aria-modal="true"' in index
    assert 'aria-labelledby="detailHeading"' in index
    assert 'aria-label="关闭"' in index
    assert "keydown" in script and "event.key === 'Enter'" in script and "event.key === ' '" in script
    assert "tabindex=\"0\"" in script
    assert "escapeHtml(colorClass" in script
    assert "function syncHoldingOptions" in script
    assert "if (!overlay.classList.contains('hidden')) return" in script
    assert "timeZone:'Asia/Shanghai'" in script
    assert "function requestDetailBars" in script and "AbortController" in script
    assert "detailRequestToken" in script
    assert "is_mock" in script
    assert "const impact = numericValue" in script
    assert ".table-wrap{overflow:auto" in css or ".table-wrap { overflow:auto" in css
    assert "@media(max-width:900px)" in (Path(__file__).parents[1] / "app" / "templates" / "report.html.j2").read_text(encoding="utf-8")


def test_d1_report_context_status_uses_observation_provenance():
    template_dir = Path(__file__).parents[1] / "app" / "templates"
    environment = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = environment.get_template("report.html.j2")
    html = template.render(
        app_name="test",
        generated_at=datetime.now(UTC),
        summary={"instrument_count": 0, "live_quote_count": 0, "market_width": {"up": 0, "down": 0}, "state_counts": {}},
        instruments=[],
        holdings=[],
        news=[],
        content_hash="test",
        market_context=[
            {
                "label": "Synthetic context",
                "enabled": True,
                "verification_status": "verified",
                "display_code": "CTX",
                "source_symbol": "CTX",
                "observation": {
                    "today_pct_change": 0.0,
                    "observed_value": 123.0,
                    "price": 123.0,
                    "source": "Mock",
                    "source_timestamp": "2026-08-29T10:00:00+08:00",
                    "fetched_at": "2026-08-29T10:00:01+08:00",
                    "freshness": "degraded",
                    "verification_status": "unverified",
                    "is_mock": True,
                },
            }
        ],
    )
    assert "Mock" in html
    assert "degraded" in html
    assert "unverified" in html
    assert "verified" not in html.split("context-status", 1)[1].split("</div>", 1)[0]


def test_report_service_generation_wires_bootstrap_market_context(bootstrapped, db_session):
    # One verified context with an observation proves the report renders the
    # bootstrap payload; the template placeholder fallback cannot produce
    # observation provenance, so this fails if market_context is not wired.
    registry = db_session.scalar(
        select(MarketContextRegistry).where(MarketContextRegistry.context_id == "us-sp500")
    )
    assert registry is not None
    registry.enabled = True
    registry.verification_status = "verified"
    registry.source_symbol = "INDEX:SP500"
    db_session.add(
        MarketContextSnapshot(
            registry_id=registry.id,
            source_symbol="INDEX:SP500",
            observed_value=5000.0,
            today_pct_change=1.23,
            source="report-test-feed",
            source_timestamp=datetime(2026, 8, 28, 9, 30, tzinfo=UTC),
            fetched_at=datetime(2026, 8, 28, 9, 31, tzinfo=UTC),
            freshness="fresh",
            verification_status="verified",
            is_mock=False,
        )
    )
    db_session.flush()
    try:
        result = ReportService().generate(db_session)
        html = Path(result["path"]).read_text(encoding="utf-8")
        assert html.count('<article class="context-card">') == 9
        for label in (
            "中国行业/板块广度与轮动",
            "上证指数",
            "沪深300",
            "中证全指",
            "S&amp;P 500",
            "Nasdaq Composite",
            "Nasdaq-100",
            "中国半导体可交易 ETF 代理",
            "韩国半导体可交易 ETF 代理",
        ):
            assert label in html
        assert "report-test-feed" in html
        assert "+1.23%" in html
        assert "registry verified" in html
        # The remaining disabled cards keep their stable disabled rendering.
        assert html.count("unavailable · disabled") == 2
    finally:
        db_session.rollback()


def test_market_context_endpoint_requires_private_auth_when_enabled(bootstrapped):
    settings = get_settings()
    old_enabled, old_token = settings.auth_enabled, settings.private_access_token
    settings.auth_enabled = True
    settings.private_access_token = "legacy-market-context-test-token-valid-1234567890"
    try:
        with TestClient(app) as client:
            assert client.get("/api/market-context").status_code == 401
            response = client.get(
                "/api/market-context", headers={"Authorization": "Bearer legacy-market-context-test-token-valid-1234567890"}
            )
            assert response.status_code == 200
            assert len(response.json()["latest_view"]) == 9
    finally:
        settings.auth_enabled, settings.private_access_token = old_enabled, old_token


def test_forecast_payload_preserves_stored_provenance_and_unavailable_cutoff(bootstrapped):
    with TestClient(app) as client:
        payload = client.get("/api/bootstrap").json()
    forecast = next(item for item in payload["instruments"] if item["forecasts"])["forecasts"]["1"]
    assert forecast["as_of_date"]
    assert forecast["generated_at"]
    assert forecast["model_version"]
    assert forecast["calibration_status"] == "not_calibrated"
    assert isinstance(forecast["sample_count"], int)
    for key in ("p_up", "expected_return", "q10", "q50", "q90"):
        assert key in forecast
    assert forecast["data_cutoff"] is None


def test_forecast_payload_does_not_trust_malformed_diagnostics_and_preserves_zero_negative_values(bootstrapped):
    with session_scope() as db:
        snapshot = db.scalar(select(ForecastSnapshot).order_by(ForecastSnapshot.id).limit(1))
        assert snapshot is not None
        snapshot.diagnostics_json = ["spoofed data_cutoff"]
        snapshot.p_up = 0.0
        snapshot.expected_return = -0.25
        snapshot.q10 = -1.0
        snapshot.q50 = 0.0
        snapshot.q90 = 0.5
        horizon = snapshot.horizon
        instrument_id = snapshot.instrument_id
    with TestClient(app) as client:
        response = client.get("/api/bootstrap")
    assert response.status_code == 200
    row = next(item for item in response.json()["instruments"] if item["id"] == instrument_id)
    forecast = row["forecasts"][str(horizon)]
    assert forecast["data_cutoff"] is None
    assert forecast["p_up"] == 0.0
    assert forecast["expected_return"] == -0.25
    assert forecast["q10"] == -1.0
    assert forecast["q50"] == 0.0
    assert forecast["q90"] == 0.5


def test_runtime_settings_can_be_changed(bootstrapped):
    with TestClient(app) as client:
        response = client.put(
            "/api/settings",
            json={
                "quote_refresh_minutes": 3,
                "signal_refresh_minutes": 10,
                "news_refresh_minutes": 30,
                "lunch_news_refresh_minutes": 10,
            },
        )
        assert response.status_code == 200
        assert response.json()["signal_refresh_minutes"] == 10


def test_d2_portfolio_ocr_review_ui_contract_is_private_and_explicit():
    static_root = Path(__file__).parents[1] / "app" / "static"
    index = (static_root / "index.html").read_text(encoding="utf-8")
    script = (static_root / "app.js").read_text(encoding="utf-8")
    css = (static_root / "app.css").read_text(encoding="utf-8")

    assert 'id="portfolioImportButton"' in index
    assert 'id="portfolioImportOverlay"' in index
    assert 'role="dialog"' in index and 'aria-modal="true"' in index
    assert 'accept="image/png,image/jpeg,image/webp"' in index
    assert "PORTFOLIO INPUT" in index
    for endpoint in (
        "/api/holding-imports",
        "/api/holding-imports/", "/candidates/",
        "/confirm",
        "/cancel",
    ):
        assert endpoint in script
    assert "instanceof FormData" in script
    assert "Content-Type" in script and "FormData" in script
    assert "uploadProgress" in script and "importBusy" in script and "importError" in script
    import_slice = script[script.index("function clearPortfolioImport"):script.index("function renderNews")]
    assert "localStorage" not in import_slice

    for marker in (
        "selected_code", "user_note", "safe_alternatives", "field_confidence",
        "matched", "ambiguous", "unmatched", "low_confidence", "duplicate", "rejected",
        "拒绝", "确认导入", "取消导入", "每一行都需要明确处理",
        "image leaves this device", "候选覆盖", "不能保存持仓", "escapeHtml",
    ):
        assert marker in index or marker in script
    assert "raw OCR" in index or "raw OCR" in script
    assert "image path" not in script.lower()
    assert "storage_key" not in script and "file.name" not in script
    assert "session_id" in script
    assert "@media (max-width:720px)" in css
    assert "prefers-reduced-motion" in css


def test_d2_race_safe_queue_numeric_and_mobile_contract():
    static_root = Path(__file__).parents[1] / "app" / "static"
    script = (static_root / "app.js").read_text(encoding="utf-8")
    css = (static_root / "app.css").read_text(encoding="utf-8")

    for marker in (
        "newImportGeneration", "abortImportRequests", "isImportCurrent", "authRequestGeneration",
        "pendingSaveTimers", "inflightSavePromises", "flushImportSaves", "resetImportWorkflow",
        "parseImportDecimal", "IMPORT_STATUS_CLASS_ALLOWLIST", "headers.delete('Content-Type')",
        "服务器最终权威判定", "MIME", "file.type", "file.size",
    ):
        assert marker in script
    assert "overflow-x:auto" in css or "overflow-x: auto" in css
    assert ".tabs { display:none" not in css and ".tabs{display:none" not in css
    for marker in (
        "sessionSaveQueue", "enqueueSessionPatch", "cancelController", "cancelPromise", "cancelError",
        "取消失败，请重试", "MIME 类型仅作浏览器提示",
    ):
        assert marker in script or marker in (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text(encoding="utf-8")
