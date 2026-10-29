from datetime import date, datetime
from zoneinfo import ZoneInfo
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import Settings, get_settings
from app.models import Hs300PassiveRatioSnapshot
from app.db.session import session_scope


def test_hs300_ratio_empty_table_returns_unavailable_no_snapshot(bootstrapped):
    with session_scope() as db:
        db.query(Hs300PassiveRatioSnapshot).delete()

    with TestClient(app) as client:
        response = client.get("/api/workspace/hs300-ratio")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unavailable"
    assert payload["reason"] == "no_snapshot"
    assert payload["items"] == []
    assert payload["research_only"] is True
    assert payload["actionable"] is False
    assert payload["changes_grade"] is False
    assert payload["qualification"] == "UNKNOWN"
    assert payload["calibration_status"] == "not_calibrated"


def test_hs300_ratio_local_bundle_returns_unavailable_not_published(bootstrapped):
    bundle_settings = Settings(_env_file=None, workspace_research_source="local_bundle")
    app.dependency_overrides[get_settings] = lambda: bundle_settings
    try:
        with TestClient(app) as client:
            response = client.get("/api/workspace/hs300-ratio")

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "unavailable"
        assert payload["reason"] == "research_ratio_not_published"
        assert payload["items"] == []
        assert payload["research_only"] is True
        assert payload["actionable"] is False
        assert payload["changes_grade"] is False
        assert payload["qualification"] == "UNKNOWN"
        assert payload["calibration_status"] == "not_calibrated"
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_hs300_ratio_read_endpoint_timing_verification_and_read_only_guarantee(bootstrapped, monkeypatch):
    # Prohibit any provider network calls during read
    def forbidden_network(*args, **kwargs):
        raise AssertionError("Read-only API must not trigger provider network calls")

    monkeypatch.setattr("urllib.request.urlopen", forbidden_network)

    test_date = date(2026, 10, 29)
    with session_scope() as db:
        db.query(Hs300PassiveRatioSnapshot).filter_by(trade_date=test_date).delete()
        # Post-close snapshot (15:30)
        db.add(
            Hs300PassiveRatioSnapshot(
                trade_date=test_date, index_code="000300.SH", basis="float_market_cap",
                numerator_basis="market_value_at_close", numerator=5_000_000,
                denominator=1_000_000_000, ratio=0.005, fund_count=2, universe_hash="a" * 64,
                constituent_count=300, constituent_as_of=date(2026, 10, 28),
                numerator_source="etf_share_scales+daily_bars:close",
                denominator_source="akshare:stock_zh_a_spot_em", lag_days=0,
                computed_at=datetime(2026, 10, 29, 15, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
                quality_hash="b" * 64,
            )
        )
        # Pre-close / morning snapshot (08:00) -> must not be marked same_day_post_close_snapshot
        db.add(
            Hs300PassiveRatioSnapshot(
                trade_date=test_date, index_code="000300.SH", basis="float_market_cap",
                numerator_basis="aum_at_nav", numerator=5_100_000,
                denominator=1_000_000_000, ratio=0.0051, fund_count=2, universe_hash="a" * 64,
                constituent_count=300, constituent_as_of=date(2026, 10, 28),
                numerator_source="fund_nav",
                denominator_source="akshare:stock_zh_a_spot_em", lag_days=0,
                computed_at=datetime(2026, 10, 29, 8, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
                quality_hash="c" * 64,
            )
        )

    try:
        with session_scope() as db:
            count_before = db.query(Hs300PassiveRatioSnapshot).count()

        with TestClient(app) as client:
            response = client.get("/api/workspace/hs300-ratio")

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "available"
        assert payload["research_only"] is True
        assert payload["actionable"] is False
        assert payload["changes_grade"] is False
        assert payload["qualification"] == "UNKNOWN"
        assert payload["calibration_status"] == "not_calibrated"
        assert len(payload["items"]) == 2

        close_item = next(item for item in payload["items"] if item["numerator_basis"] == "market_value_at_close")
        assert close_item["ratio"] == 0.005
        assert close_item["observation_kind"] == "same_day_post_close_snapshot"

        nav_item = next(item for item in payload["items"] if item["numerator_basis"] == "aum_at_nav")
        assert nav_item["ratio"] == 0.0051
        assert nav_item["observation_kind"] == "research_snapshot"

        # Verify read-only guarantee: no database insertions, updates, or deletes
        with session_scope() as db:
            count_after = db.query(Hs300PassiveRatioSnapshot).count()
        assert count_before == count_after
    finally:
        with session_scope() as db:
            db.query(Hs300PassiveRatioSnapshot).filter_by(trade_date=test_date).delete()
