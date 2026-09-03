from __future__ import annotations

from app.services.etf_1430_service import ETF1430WorkbenchService
from app.services.kline_stabilization_service import KlineStabilizationService


def test_compatibility_services_share_the_same_current_action(bootstrapped, db_session) -> None:
    etf_rows = {
        row["ts_code"]: row
        for row in ETF1430WorkbenchService().summary(db_session)["rows"]
    }
    kline_rows = {
        row["ts_code"]: row
        for row in KlineStabilizationService().summary(db_session)["rows"]
    }

    common = sorted(set(etf_rows) & set(kline_rows))
    assert common
    for code in common:
        left = etf_rows[code]
        right = kline_rows[code]
        assert left["action"] == right["action"]
        assert left["action_source"] == right["action_source"]
        assert left["decision_snapshot_id"] == right["decision_snapshot_id"]


def test_compatibility_forecasts_never_recompute_an_alternate_dynamic_model(bootstrapped, db_session) -> None:
    etf_summary = ETF1430WorkbenchService().summary(db_session)
    kline_summary = KlineStabilizationService().summary(db_session)

    for row in etf_summary["rows"]:
        for forecast in row["forecasts"].values():
            assert forecast["source"] in {"persisted_forecast_snapshot", "unavailable"}
            assert forecast["source"] != "dynamic_similarity_research"

    for row in kline_summary["rows"]:
        assert row["forecast"]["source"] in {"persisted_forecast_snapshot", "unavailable"}
