from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_dashboard_api_and_static_assets(bootstrapped):
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        dashboard = client.get("/api/bootstrap")
        assert dashboard.status_code == 200
        payload = dashboard.json()
        assert payload["summary"]["instrument_count"] >= 9
        assert payload["instruments"]
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
