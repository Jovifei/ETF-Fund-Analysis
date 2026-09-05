from __future__ import annotations

from pathlib import Path

from app.main import app
from app.services.etf_1430_service import ETF1430WorkbenchService
from fastapi.testclient import TestClient


def test_etf_1430_summary_and_detail_contract(bootstrapped, db_session):
    service = ETF1430WorkbenchService()
    summary = service.summary(db_session)
    assert summary["forecast_horizons"] == [1, 3, 5, 10]
    assert summary["automatic_orders"] is False
    assert summary["historical_1430_backtest"] == "not_qualified"
    assert summary["rows"]
    row = summary["rows"][0]
    assert row["action"] in {"可加仓", "可入场", "可试探", "观望", "减仓", "数据异常"}
    assert row["action_source"] in {"decision_board_snapshot", "signal_grade_fallback", "signal_snapshot_last_resort", "unavailable"}
    assert row["score_semantics"] == "explanatory_ranking_only_not_current_decision"
    assert row["actionable"] is False  # mock provider must fail closed
    assert set(row["component_scores"]) == {"trend", "momentum", "volume_flow", "structure", "forecast", "news"}
    assert set(row["forecasts"]) == {"1", "3", "5", "10"}
    assert all(item["source"] in {"persisted_forecast_snapshot", "unavailable"} for item in row["forecasts"].values())
    assert not any(item["source"] == "dynamic_similarity_research" for item in row["forecasts"].values())
    for item in row["forecasts"].values():
        if item["source"] == "persisted_forecast_snapshot":
            assert item["p_up_semantics"] in {"weighted_historical_neighbor_up_frequency", "calibrated_up_probability"}

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
        for route in ("/workbench/1430", "/workbench/kline", "/legacy"):
            page = client.get(route, follow_redirects=False)
            assert page.status_code == 200
        home = client.get("/")
        assert home.status_code == 200
        assert 'href="/legacy"' in home.text
        assert "统一决策台" in home.text
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
