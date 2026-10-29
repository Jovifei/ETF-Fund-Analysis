from datetime import date, datetime, time
from zoneinfo import ZoneInfo
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.main import app
from app.core.config import Settings, get_settings
from app.db.session import get_engine, session_scope
from app.models import Hs300PassiveRatioSnapshot
from app.services.settlement import SETTLEMENT_CUTOFF


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


def test_hs300_ratio_settlement_cutoff_boundary_and_zero_side_effect_guarantee(bootstrapped, monkeypatch):
    # 1. Prohibit all external network clients and provider invocations
    def forbidden_call(*args, **kwargs):
        raise AssertionError("Read-only API must not trigger external network or provider calls")

    monkeypatch.setattr("urllib.request.urlopen", forbidden_call)
    try:
        import requests
        monkeypatch.setattr("requests.sessions.Session.request", forbidden_call)
        monkeypatch.setattr("requests.get", forbidden_call)
        monkeypatch.setattr("requests.post", forbidden_call)
    except ImportError:
        pass
    try:
        import httpx
        orig_httpx = httpx.Client.request
        def safe_httpx(self, method, url, *args, **kwargs):
            if not str(url).startswith("http://testserver"):
                raise AssertionError(f"Read-only API must not trigger external HTTP requests: {url}")
            return orig_httpx(self, method, url, *args, **kwargs)
        monkeypatch.setattr("httpx.Client.request", safe_httpx)
        monkeypatch.setattr("httpx.AsyncClient.request", forbidden_call)
    except ImportError:
        pass
    monkeypatch.setattr("app.services.hs300_ratio_service.Hs300RatioService.refresh", forbidden_call)
    monkeypatch.setattr("app.services.hs300_ratio_service.Hs300RatioService._fetch_market_caps", forbidden_call)
    monkeypatch.setattr("app.services.hs300_ratio_service.Hs300RatioService._fetch_constituents", forbidden_call)
    monkeypatch.setattr("app.services.hs300_ratio_service.Hs300RatioService._fetch_navs", forbidden_call)

    test_date = date(2026, 10, 29)
    tz = ZoneInfo("Asia/Shanghai")

    # 2. Seed records with various timestamps to test exact SETTLEMENT_CUTOFF boundaries
    with session_scope() as db:
        db.query(Hs300PassiveRatioSnapshot).filter_by(trade_date=test_date).delete()
        # Case A: exactly at cutoff (15:15:00) -> same_day_post_close_snapshot
        db.add(
            Hs300PassiveRatioSnapshot(
                trade_date=test_date, index_code="000300.SH", basis="float_market_cap",
                numerator_basis="market_value_at_close", numerator=5_000_000,
                denominator=1_000_000_000, ratio=0.005, fund_count=2, universe_hash="a" * 64,
                constituent_count=300, constituent_as_of=date(2026, 10, 28),
                numerator_source="etf_share_scales+daily_bars:close",
                denominator_source="akshare:stock_zh_a_spot_em", lag_days=0,
                computed_at=datetime(2026, 10, 29, 15, 15, 0, tzinfo=tz),
                quality_hash="b" * 64,
            )
        )
        # Case B: 1 second before cutoff (15:14:59) -> research_snapshot (must not be marked post-close)
        db.add(
            Hs300PassiveRatioSnapshot(
                trade_date=test_date, index_code="000300.SH", basis="float_market_cap",
                numerator_basis="aum_at_nav", numerator=5_100_000,
                denominator=1_000_000_000, ratio=0.0051, fund_count=2, universe_hash="a" * 64,
                constituent_count=300, constituent_as_of=date(2026, 10, 28),
                numerator_source="fund_nav",
                denominator_source="akshare:stock_zh_a_spot_em", lag_days=0,
                computed_at=datetime(2026, 10, 29, 15, 14, 59, tzinfo=tz),
                quality_hash="c" * 64,
            )
        )
        # Case C: morning (08:00:00) on trade date -> research_snapshot
        db.add(
            Hs300PassiveRatioSnapshot(
                trade_date=test_date, index_code="000300.SH", basis="float_market_cap",
                numerator_basis="morning_trial", numerator=5_050_000,
                denominator=1_000_000_000, ratio=0.00505, fund_count=2, universe_hash="a" * 64,
                constituent_count=300, constituent_as_of=date(2026, 10, 28),
                numerator_source="trial",
                denominator_source="trial", lag_days=0,
                computed_at=datetime(2026, 10, 29, 8, 0, 0, tzinfo=tz),
                quality_hash="d" * 64,
            )
        )

    # 3. Intercept all SQL execution to guarantee zero write statements (no INSERT/UPDATE/DELETE)
    writes_detected = []
    def monitor_sql_writes(conn, clauseelement, multiparams, params, execution_options):
        raw_sql = str(clauseelement).strip().upper()
        if raw_sql.startswith(("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE")):
            writes_detected.append(raw_sql)

    engine = get_engine()
    event.listen(engine, "before_execute", monitor_sql_writes)

    try:
        # Snapshot full row values before query to ensure no row was modified
        with session_scope() as db:
            rows_before = [
                (r.id, r.trade_date, r.numerator_basis, r.ratio, r.computed_at)
                for r in db.query(Hs300PassiveRatioSnapshot).order_by(Hs300PassiveRatioSnapshot.id.asc()).all()
            ]

        with TestClient(app) as client:
            response = client.get("/api/workspace/hs300-ratio")

        # Snapshot full row values after query
        with session_scope() as db:
            rows_after = [
                (r.id, r.trade_date, r.numerator_basis, r.ratio, r.computed_at)
                for r in db.query(Hs300PassiveRatioSnapshot).order_by(Hs300PassiveRatioSnapshot.id.asc()).all()
            ]

        # Verify no database mutation happened
        assert len(writes_detected) == 0, f"Write queries detected: {writes_detected}"
        assert rows_before == rows_after, "Database rows were modified during read-only call"

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "available"
        assert payload["research_only"] is True
        assert payload["actionable"] is False
        assert payload["changes_grade"] is False
        assert payload["qualification"] == "UNKNOWN"
        assert payload["calibration_status"] == "not_calibrated"
        assert len(payload["items"]) == 3

        item_exact_cutoff = next(i for i in payload["items"] if i["numerator_basis"] == "market_value_at_close")
        assert item_exact_cutoff["observation_kind"] == "same_day_post_close_snapshot"

        item_before_cutoff = next(i for i in payload["items"] if i["numerator_basis"] == "aum_at_nav")
        assert item_before_cutoff["observation_kind"] == "research_snapshot"

        item_morning = next(i for i in payload["items"] if i["numerator_basis"] == "morning_trial")
        assert item_morning["observation_kind"] == "research_snapshot"
    finally:
        event.remove(get_engine(), "before_execute", monitor_sql_writes)
        with session_scope() as db:
            db.query(Hs300PassiveRatioSnapshot).filter_by(trade_date=test_date).delete()
