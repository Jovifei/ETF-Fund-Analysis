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
        tail = client.get("/decision/1430", follow_redirects=False)
        assert tail.status_code == 200
        assert "14:30 尾盘模式" in tail.text

        compatibility = client.get("/workbench/1430", follow_redirects=False)
        assert compatibility.status_code == 307
        assert compatibility.headers["location"] == "/decision/1430"

        legacy = client.get("/legacy", follow_redirects=False)
        assert legacy.status_code == 307
        assert legacy.headers["location"] == "/research"
        research = client.get("/research", follow_redirects=False)
        assert research.status_code == 200
        assert "ETF 研究中心" in research.text

        retired = client.get("/workbench/kline", follow_redirects=False)
        assert retired.status_code == 307 and retired.headers["location"] == "/"

        home = client.get("/")
        assert home.status_code == 200
        assert 'href="/legacy"' not in home.text
        # 主导航由统一壳 JS 渲染：断言壳脚本包含全部一级链接（单一来源）
        shell_js = client.get("/assets/app_shell.js")
        assert shell_js.status_code == 200
        for link in ('/boards', '/holdings', '/research', '/account'):
            assert f"href: '{link}'" in shell_js.text
        # 尾盘模式/统一决策台文案来自决策页 JS 壳配置
        workbuddy_js = client.get("/assets/decision_board_workbuddy.js")
        assert workbuddy_js.status_code == 200
        assert "尾盘模式" in workbuddy_js.text
        assert "/decision/1430" in workbuddy_js.text

        script = client.get("/assets/etf_1430_workbench.js")
        assert script.status_code == 200
        assert "预测情景 · 非实际结果" in script.text
        assert "历史上涨占比" in script.text
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


def test_etf_detail_page_route_and_contract(bootstrapped):
    """全站唯一 ETF 详情页 /etf/{ts_code}（决策/板块/持仓/14:30 共用）。"""
    with TestClient(app) as client:
        page = client.get("/etf/512480.SH")
        assert page.status_code == 200
        assert "ETF 详情 · 研究研判台" in page.text
        assert 'src="/assets/etf_detail.js' in page.text
        assert 'id="shellTopbar"' in page.text and "/assets/app_shell.js" in page.text
        script = client.get("/assets/etf_detail.js")
        assert script.status_code == 200
        assert "/api/workbench/1430/" in script.text
        assert "预测情景 · 非实际结果" in script.text
