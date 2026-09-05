"""PR-D：用户自选关注 + 持仓页融合（当前动作/预测/支撑压力）。

认证关闭的测试环境下 user_id=None（系统/匿名池），语义与 Holding 一致。
"""
from __future__ import annotations

import pytest
from app.main import app
from app.services.watchlist_service import WatchlistService
from fastapi.testclient import TestClient


def test_watchlist_add_mock_resolve_and_duplicate(bootstrapped, db_session):
    """Mock provider 能解析 watchlist 内的代码；重复添加返回 duplicate 标记。"""
    service = WatchlistService()
    entry = service.add(db_session, code="512480.SH", note="测试半导体")
    db_session.commit()
    assert entry["ts_code"] == "512480.SH"
    assert entry["name"] == "半导体ETF"
    assert entry["duplicate"] is False

    again = service.add(db_session, code="512480", note=None)
    db_session.commit()
    assert again["duplicate"] is True and again["id"] == entry["id"]

    listed = service.list_entries(db_session)
    assert [row["ts_code"] for row in listed] == ["512480.SH"]


def test_watchlist_unknown_code_fails_closed(bootstrapped, db_session):
    """Mock 环境下未知代码 fail-closed（无法解析即拒绝，不瞎建标的）。"""
    service = WatchlistService()
    with pytest.raises(Exception) as exc:
        service.add(db_session, code="999999.SH")
    assert "识别" in str(exc.value)


def test_watchlist_delete_scoped(bootstrapped, db_session):
    service = WatchlistService()
    entry = service.add(db_session, code="510300.SH")
    db_session.commit()
    assert service.delete(db_session, entry["id"]) is True
    db_session.commit()
    assert service.delete(db_session, entry["id"]) is False


def test_watchlist_api_endpoints(bootstrapped):
    with TestClient(app) as client:
        added = client.post("/api/watchlist/entries", json={"code": "510300.SH", "note": "门控基准"})
        assert added.status_code == 201
        body = added.json()
        assert body["entry"]["ts_code"] == "510300.SH"

        listed = client.get("/api/watchlist")
        assert listed.status_code == 200
        assert any(row["ts_code"] == "510300.SH" for row in listed.json())

        entry_id = body["entry"]["id"]
        removed = client.delete(f"/api/watchlist/entries/{entry_id}")
        assert removed.status_code == 200
        missing = client.delete(f"/api/watchlist/entries/{entry_id}")
        assert missing.status_code == 404

        bad = client.post("/api/watchlist/entries", json={"code": "999999.SH"})
        assert bad.status_code == 422


def test_holdings_endpoint_enriches_action_and_forecasts(bootstrapped, db_session):
    """持仓行带 canonical action + 1/3/5/10 预测 + 支撑/压力（读快照，零计算）。"""
    with TestClient(app) as client:
        put = client.put(
            "/api/holdings/510300.SH",
            json={"ts_code": "510300.SH", "shares": 10000, "cost_price": 3.9},
        )
        assert put.status_code == 200
        rows = client.get("/api/holdings").json()
        row = next(r for r in rows if r["ts_code"] == "510300.SH")
        assert "current_action" in row
        assert set(row["forecasts"]) == {"1", "3", "5", "10"}
        for item in row["forecasts"].values():
            assert item["calibration_status"] in {"not_calibrated", "calibrated"}
        assert "nearest_support" in row and "nearest_resistance" in row
