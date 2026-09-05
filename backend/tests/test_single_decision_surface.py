from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services.etf_1430_service import ETF1430WorkbenchService
from app.services.kline_stabilization_service import KlineStabilizationService
from app.services.signal_center_service import SignalCenterService


def test_all_research_entrypoints_are_accessible_and_render_expected_surfaces() -> None:
    client = TestClient(app)
    expected_matches = {
        "/": "decision_board_workbuddy.js",
        "/legacy": "中国 ETF/LOF 私有决策看板",
        "/workbench/1430": "ETF 14:30 决策工作台",
        "/workbench/kline": "kline_stabilization.js",
        "/assets/index.html": "中国 ETF/LOF 私有决策看板",
        "/assets/etf_1430_workbench.html": "ETF 14:30 决策工作台",
        "/assets/kline_stabilization.html": "kline_stabilization.js",
    }
    for path, expected_token in expected_matches.items():
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 200, f"{path} failed with {response.status_code}"
        assert expected_token in response.text, f"{expected_token} not in {path}"


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
