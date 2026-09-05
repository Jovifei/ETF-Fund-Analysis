"""PR-G：多周期分钟线（MarketBar + /minute-bars + 周期切换契约）。

真实性契约：日K 永不冒充分钟线；未同步分钟区间 available=false；
mock 来源显式标注 contains_mock。
"""
from __future__ import annotations

from datetime import date

from app.main import app
from app.providers.mock import MockProvider
from app.services.market_bar_service import MarketBarService
from fastapi.testclient import TestClient


def test_mock_minute_bars_roundtrip(bootstrapped, db_session):
    service = MarketBarService(provider=MockProvider())
    result = service.sync_minute_bars(db_session, ["510300.SH"], "30m", window_days=5)
    db_session.commit()
    assert result["status"] == "succeeded"  # mock 不受 minute_bars_enabled 限制
    assert result["inserted"] > 0

    read = service.read_minute_bars(db_session, "510300.SH", "30m")
    assert read["available"] is True
    assert read["contains_mock"] is True
    assert all(item["source"] == "mock:minute" for item in read["bars"])
    for bar in read["bars"]:
        assert bar["high"] >= max(bar["open"], bar["close"])
        assert bar["low"] <= min(bar["open"], bar["close"])

    unsupported = service.read_minute_bars(db_session, "510300.SH", "60m")
    assert unsupported["available"] is False  # 只同步了 30m，60m 诚实不可用


def test_minute_sync_disabled_by_default_for_real_providers(db_session):
    """生产契约：MINUTE_BARS_ENABLED=false 时真实 provider 同步跳过（日K 不冒充分钟线）。"""

    class _FakeProvider(MockProvider):
        name = "akshare"

        def __init__(self):  # 绕过 settings 依赖
            pass

        def fetch_minute_bars(self, ts_code, interval, start_date, end_date):
            raise AssertionError("disabled sync must not call the provider")

    service = MarketBarService(provider=_FakeProvider())
    result = service.sync_minute_bars(db_session, ["510300.SH"], "30m")
    assert result["status"] == "skipped"
    assert "MINUTE_BARS_ENABLED" in result["reason"]


def test_minute_bars_api_contract(bootstrapped):
    with TestClient(app) as client:
        # 159915.SZ 不被本文件其它测试同步——保证"未同步=不可用"契约稳定。
        empty = client.get("/api/instruments/159915.SZ/minute-bars?interval=30m")
        assert empty.status_code == 200
        payload = empty.json()
        assert payload["available"] is False
        assert payload["bars"] == []

        bad_interval = client.get("/api/instruments/159915.SZ/minute-bars?interval=5m")
        assert bad_interval.status_code == 422

        daily = client.get("/api/instruments/510300.SH/bars?limit=25")
        assert daily.status_code == 200
        assert isinstance(daily.json(), list) and len(daily.json()) == 25


def test_minute_bars_roundtrip_via_api(bootstrapped, db_session):
    service = MarketBarService(provider=MockProvider())
    service.sync_minute_bars(db_session, ["510300.SH"], "60m", window_days=5)
    db_session.commit()
    with TestClient(app) as client:
        payload = client.get("/api/instruments/510300.SH/minute-bars?interval=60m").json()
        assert payload["available"] is True
        assert payload["contains_mock"] is True
        assert len(payload["bars"]) >= 10
