from __future__ import annotations

import json
from pathlib import Path

from app.services.strategy_family_replay_backtest_service import StrategyFamilyReplayBacktestService


def test_strategy_family_replay_uses_runtime_family_contract(bootstrapped, db_session):
    result = StrategyFamilyReplayBacktestService().run(db_session, run_id="test-strategy-family-replay")
    payload = json.loads(Path(result["path"]).read_text(encoding="utf-8"))
    contract = payload["audit"]["strategy_replay_contract"]
    assert contract["status"] == "family_selector_replay_partial"
    assert contract["actionable"] is False
    assert contract["calibration_status"] == "not_calibrated"
    assert "forecast_news_holding_state_not_replayed" in contract["reason"]
    assert payload["qualification"] == "UNKNOWN"
