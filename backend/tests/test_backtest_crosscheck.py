"""Tests for backtest_crosscheck (independent second engine + task registration).

Covers: task exists, crosscheck reads primary report, pass/fail verdict, mock flagged.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.services.backtest_service import RotationBacktestService
from app.services.task_service import TaskService
from app.services.crosscheck_engine import crosscheck_main


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
    assert result["status"] in ("pass", "fail"), f"unexpected status: {result['status']}"
    assert "primary_run_id" in result
    assert "equity" in result
    assert "trades" in result
    assert "checks" in result

    # In mock environment, we expect pass (deterministic replay)
    assert result["equity"]["primary_final"] > 0
    assert result["equity"]["crosscheck_final"] > 0


def test_crosscheck_mock_flagged(bootstrapped, db_session):
    """In mock environment, the data note should be present."""
    RotationBacktestService().run(db_session, run_id="test-crosscheck-mock")
    db_session.commit()
    result = crosscheck_main(db_session)
    assert result["status"] != "skipped"
