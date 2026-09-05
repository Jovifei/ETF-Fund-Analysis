from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services.etf_1430_service import ETF1430WorkbenchService
from app.services.kline_stabilization_service import KlineStabilizationService
from app.services.signal_center_service import SignalCenterService


APP_SHELL_ASSET = "/assets/app_shell.js?v=0.8.0-nav1"


def test_all_research_entrypoints_are_accessible_and_render_expected_surfaces() -> None:
    client = TestClient(app)
    expected_matches = {
        "/": "decision_board_workbuddy.js",
        "/legacy": "中国 ETF/LOF 私有决策看板",
        "/workbench/1430": "ETF 14:30 决策工作台",
        "/boards": "行业板块 · 板块市场",
        "/etf/510300.SH": "ETF 详情 · 研究研判台",
        "/assets/index.html": "中国 ETF/LOF 私有决策看板",
        "/assets/etf_1430_workbench.html": "ETF 14:30 决策工作台",
    }
    for path, expected_token in expected_matches.items():
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 200, f"{path} failed with {response.status_code}"
        assert expected_token in response.text, f"{expected_token} not in {path}"

    # PR-I：K线研判页下线——307 到 /boards（详情台承接 K 线，板块页承接宽度）
    for retired in ("/workbench/kline", "/assets/kline_stabilization.html"):
        response = client.get(retired, follow_redirects=False)
        assert response.status_code == 307, f"{retired} expected 307, got {response.status_code}"
        assert response.headers["location"] == "/boards"


def test_navigation_shell_has_four_primary_entries_plus_1430_task() -> None:
    client = TestClient(app)

    # 用户可记忆的稳定入口：四个一级业务入口 + 一个 14:30 任务入口。
    portfolio = client.get("/portfolio", follow_redirects=False)
    research = client.get("/research", follow_redirects=False)
    assert portfolio.status_code == 307
    assert portfolio.headers["location"] == "/legacy#holdings"
    assert research.status_code == 307
    assert research.headers["location"] == "/legacy#signals"

    # 每个用户可见页面都加载同一份 App Shell；不再由各页面各自定义跳转语义。
    for path in ("/", "/boards", "/legacy", "/workbench/1430", "/etf/510300.SH"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 200
        assert APP_SHELL_ASSET in response.text

    shell = client.get("/assets/app_shell.js")
    assert shell.status_code == 200
    for required in (
        "/portfolio",
        "/research",
        "/workbench/1430",
        ".decision-data-row[data-code]",
        "#decisionRows tr[data-code]",
        "#gradeGroups tr[data-code]",
        "#holdings",
        "#signals",
    ):
        assert required in shell.text


def test_all_current_research_surfaces_share_the_same_action(bootstrapped, db_session) -> None:
    etf_summary = ETF1430WorkbenchService().summary(db_session)
    kline_summary = KlineStabilizationService().summary(db_session)
    signal_summary = SignalCenterService().build(db_session)

    etf_rows = {row["ts_code"]: row for row in etf_summary["rows"]}
    kline_rows = {row["ts_code"]: row for row in kline_summary["rows"]}
    signal_states = signal_summary["current_states"]

    common = sorted(set(etf_rows) & set(kline_rows) & set(signal_states))
    assert common
    for code in common:
        etf_row = etf_rows[code]
        kline_row = kline_rows[code]
        signal_state = signal_states[code]

        assert etf_row["action"] == kline_row["action"] == signal_state["state"]
        assert etf_row["action_source"] == kline_row["action_source"] == signal_state["source"]
        assert etf_row["decision_snapshot_id"] == kline_row["decision_snapshot_id"]
        assert etf_row["decision_snapshot_id"] == signal_summary["decision_snapshot_id"]


def test_compatibility_forecasts_never_recompute_an_alternate_dynamic_model(bootstrapped, db_session) -> None:
    etf_summary = ETF1430WorkbenchService().summary(db_session)
    kline_summary = KlineStabilizationService().summary(db_session)

    for row in etf_summary["rows"]:
        for forecast in row["forecasts"].values():
            assert forecast["source"] in {"persisted_forecast_snapshot", "unavailable"}
            assert forecast["source"] != "dynamic_similarity_research"

    for row in kline_summary["rows"]:
        assert row["forecast"]["source"] in {"persisted_forecast_snapshot", "unavailable"}
