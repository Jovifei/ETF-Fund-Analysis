from __future__ import annotations

from pathlib import Path

from app.services.backtest_service import RotationBacktestService


def test_rotation_backtest_is_next_open_and_audited(bootstrapped, db_session):
    result = RotationBacktestService().run(db_session, run_id="test-rotation-backtest")
    db_session.commit()
    assert result["decision_count"] > 10
    assert result["metrics"]["trade_count"] > 0
    assert Path(result["path"]).is_file()

    payload = __import__("json").loads(Path(result["path"]).read_text(encoding="utf-8"))
    assert payload["audit"]["decision_at"] == "close_t"
    assert payload["audit"]["execution_at"] == "open_t_plus_1"
    assert payload["audit"]["future_data_in_features"] is False
    assert payload["data"]["contains_mock"] is True
    assert all(item["feature_date_max"] == item["as_of_close"] for item in payload["decisions"])
    assert all(item["execution_date"] > item["as_of_close"] for item in payload["decisions"])
