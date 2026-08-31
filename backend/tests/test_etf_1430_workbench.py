from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.etf_1430_service import ETF1430WorkbenchService


def test_etf_1430_summary_and_detail_contract(bootstrapped, db_session):
    service = ETF1430WorkbenchService()
    summary = service.summary(db_session)
    assert summary["forecast_horizons"] == [1, 3, 5, 10]
    assert summary["automatic_orders"] is False
    assert summary["historical_1430_backtest"] == "not_qualified"
    assert summary["rows"]
    row = summary["rows"][0]
    assert row["action"] in {"买入候选", "可试探", "持有/观察", "减仓候选", "回避"}
    assert row["actionable"] is False  # mock provider must fail closed
    assert set(row["component_scores"]) == {"trend", "momentum", "volume_flow", "structure", "forecast", "news"}
    assert set(row["forecasts"]) == {"1", "3", "5", "10"}
    assert all(item["calibration_status"] == "not_calibrated" for item in row["forecasts"].values())

    detail = service.detail(db_session, row["ts_code"])
    assert detail is not None
    assert detail["chart"]["historical"]
    assert len(detail["chart"]["forecast_scenario"]) == 10
    assert all(item["is_forecast"] and item["not_actual"] for item in detail["chart"]["forecast_scenario"])
    for candle in detail["chart"]["forecast_scenario"]:
        assert candle["low"] <= min(candle["open"], candle["close"])
        assert candle["high"] >= max(candle["open"], candle["close"])
    assert "chan_zone_approx" in detail["support_resistance"]


def test_etf_1430_http_and_static_contract(bootstrapped):
    with TestClient(app) as client:
        page = client.get("/workbench/1430")
        assert page.status_code == 200
        assert "ETF 14:30 决策工作台" in page.text
        script = client.get("/assets/etf_1430_workbench.js")
        assert script.status_code == 200
        assert "预测情景 · 非实际结果" in script.text
        summary = client.get("/api/workbench/1430/summary")
        assert summary.status_code == 200
        payload = summary.json()
        code = payload["rows"][0]["ts_code"]
        detail = client.get(f"/api/workbench/1430/{code}")
        assert detail.status_code == 200
        generated = client.post("/api/workbench/1430/generate")
        assert generated.status_code == 200
        assert generated.json()["research_only"] is True


def test_etf_1430_required_operational_files_exist():
    root = Path(__file__).resolve().parents[2]
    required = [
        "config/etf_1430_workbench.json",
        "scripts/generate_1430_decision.py",
        "scripts/run_1430_decision.sh",
        "scripts/build_1430_point_in_time_dataset.py",
        "deploy/systemd/etf-1430-decision.service",
        "deploy/systemd/etf-1430-decision.timer",
        "docs/ETF_1430_DECISION_WORKBENCH.md",
        "docs/SUPPORT_RESISTANCE_SEMANTICS.md",
        "docs/LOCAL_AGENT_PROMPT_ETF_1430.md",
    ]
    missing = [item for item in required if not (root / item).is_file()]
    assert missing == []
