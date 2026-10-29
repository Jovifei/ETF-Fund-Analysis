from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.main import app
from app.models import Hs300PassiveRatioSnapshot
from app.db.session import session_scope


def test_hs300_ratio_read_endpoint_is_research_only_and_does_not_fetch(bootstrapped):
    with session_scope() as db:
        db.add(
            Hs300PassiveRatioSnapshot(
                trade_date=date(2026, 10, 29), index_code="000300.SH", basis="float_market_cap",
                numerator_basis="market_value_at_close", numerator=5_000_000,
                denominator=1_000_000_000, ratio=0.005, fund_count=2, universe_hash="a" * 64,
                constituent_count=300, constituent_as_of=date(2026, 10, 28),
                numerator_source="etf_share_scales+daily_bars:close",
                denominator_source="akshare:stock_zh_a_spot_em", lag_days=0,
                computed_at=datetime(2026, 10, 29, 8, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
                quality_hash="b" * 64,
            )
        )

    try:
        with TestClient(app) as client:
            response = client.get("/api/workspace/hs300-ratio")

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "available"
        assert payload["research_only"] is True
        assert payload["actionable"] is False
        assert payload["changes_grade"] is False
        assert payload["qualification"] == "UNKNOWN"
        assert payload["items"][0]["ratio"] == 0.005
        assert payload["items"][0]["observation_kind"] == "same_day_post_close_snapshot"
    finally:
        with session_scope() as db:
            db.query(Hs300PassiveRatioSnapshot).filter_by(trade_date=date(2026, 10, 29)).delete()

