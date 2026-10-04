"""Tests for backtest_crosscheck (independent second engine + task registration).

Covers: task exists, crosscheck reads primary report, pass/fail verdict, mock flagged.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.services.backtest_service import RotationBacktestService
from app.services.task_service import TaskService
from app.services.crosscheck_engine import CrosscheckEngine, crosscheck_main


def test_backtest_crosscheck_task_exists():
    assert "backtest_crosscheck" in TaskService().task_names


def test_crosscheck_read_primary_and_verdict(bootstrapped, db_session):
    """Crosscheck reads the primary backtest report and produces a verdict."""
    # First: run the primary backtest
    primary = RotationBacktestService().run(db_session, run_id="test-crosscheck-primary")
    db_session.commit()
    assert primary["decision_count"] > 0

    # Now: run the crosscheck
    result = crosscheck_main(db_session)
    db_session.commit()
    assert result["status"] == "pass", result
    assert "primary_run_id" in result
    assert "equity" in result
    assert "trades" in result
    assert "checks" in result

    # In mock environment, we expect pass (deterministic replay)
    assert result["equity"]["primary_final"] > 0
    assert result["equity"]["crosscheck_final"] > 0
    assert all(result["checks"].values()), result["checks"]
    assert result["equity"]["max_curve_difference_pct"] <= result["equity"]["threshold_pct"]
    assert result["slippage"]["primary_total"] >= 0
    assert result["slippage"]["crosscheck_total"] >= 0
    assert result["primary_content_hash"]
    assert result["actionable"] is False


def test_crosscheck_mock_flagged(bootstrapped, db_session):
    """In mock environment, the data note should be present."""
    RotationBacktestService().run(db_session, run_id="test-crosscheck-mock")
    db_session.commit()
    result = crosscheck_main(db_session)
    assert result["status"] == "pass"
    assert result["qualification"] == "mock_or_synthetic"
    assert result["actionable"] is False


def test_crosscheck_fails_if_primary_daily_inputs_changed_after_report(bootstrapped, db_session):
    from sqlalchemy import select
    from app.models import DailyBar, Instrument

    primary = RotationBacktestService().run(db_session, run_id="test-crosscheck-lineage")
    db_session.commit()
    payload = json.loads(Path(primary["path"]).read_text(encoding="utf-8"))
    code = next(iter(payload["data"]["input_hashes"]))
    inst = db_session.scalar(select(Instrument).where(Instrument.ts_code == code))
    assert inst is not None
    bar = db_session.scalars(
        select(DailyBar).where(DailyBar.instrument_id == inst.id).order_by(DailyBar.trade_date)
    ).first()
    assert bar is not None
    original = bar.close
    bar.close = float(original) * 1.001
    db_session.flush()

    result = CrosscheckEngine().run(db_session)
    assert result["status"] == "fail"
    assert result["reason"] == "primary_inputs_changed"
    assert code in result["mismatched_codes"]
    assert result["actionable"] is False
    db_session.rollback()
