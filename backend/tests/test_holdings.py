from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_holding_crud(bootstrapped):
    payload = {
        "ts_code": "510300.SH",
        "shares": 1000,
        "cost_price": 4.1,
        "target_weight": 0.15,
        "notes": "测试持仓",
    }
    with TestClient(app) as client:
        response = client.put("/api/holdings/510300.SH", json=payload)
        assert response.status_code == 200
        holdings = client.get("/api/holdings").json()
        assert any(item["ts_code"] == "510300.SH" for item in holdings)
        deleted = client.delete("/api/holdings/510300.SH")
        assert deleted.status_code == 200 and deleted.json()["deleted"] is True
