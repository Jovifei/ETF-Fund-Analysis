"""Tests for shadow_run_audit (shadow_run_audit_service + task registration).

Covers: task exists, audit produced, summary fields present, research-only invariant.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.services.shadow_run_audit_service import ShadowRunAuditService
from app.services.task_service import TaskService


def test_shadow_run_audit_task_exists():
    assert "shadow_run_audit" in TaskService().task_names


def test_shadow_audit_produces_report(bootstrapped, db_session):
    svc = ShadowRunAuditService()
    result = svc.run(db_session, run_id="test-shadow-audit")
    db_session.commit()
    assert result["run_id"] == "test-shadow-audit"
    assert result["is_trade_day"] is not None
    assert "summary" in result
    assert result["summary"]["total_instruments"] > 0
    assert "path" in result

    payload = json.loads(Path(result["path"]).read_text(encoding="utf-8"))
    assert payload["research_status"] == "shadow_only_no_production_changes"
    assert payload["promotion_policy"] is not None
    assert len(payload["audits"]) == result["summary"]["audited"]


def test_shadow_audit_no_production_writes(bootstrapped, db_session):
    """Shadow audit must NOT modify forecast calibration_status or signal state."""
    from app.models import ForecastSnapshot, SignalSnapshot
    from sqlalchemy import select

    # Capture pre-audit state
    pre_cal = {
        row.id: row.calibration_status
        for row in db_session.scalars(select(ForecastSnapshot)).all()
    }
    pre_sig_state = {
        row.id: row.state for row in db_session.scalars(select(SignalSnapshot)).all()
    }

    svc = ShadowRunAuditService()
    svc.run(db_session, run_id="test-no-write")
    db_session.commit()

    # Verify no modification
    post_cal = {
        row.id: row.calibration_status
        for row in db_session.scalars(select(ForecastSnapshot)).all()
    }
    post_sig_state = {
        row.id: row.state for row in db_session.scalars(select(SignalSnapshot)).all()
    }
    assert pre_cal == post_cal, "forecast calibration_status was modified!"
    assert pre_sig_state == post_sig_state, "signal state was modified!"
