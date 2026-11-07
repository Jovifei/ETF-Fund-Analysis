"""Tests for shadow_run_audit (shadow_run_audit_service + task registration).

Covers: task exists, audit produced, summary fields present, research-only invariant.
"""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timedelta

import pytest

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


def test_shadow_audit_default_target_uses_configured_timezone(bootstrapped, db_session):
    svc = ShadowRunAuditService()
    result = svc.run(db_session, run_id="test-shadow-timezone")
    expected = datetime.now(svc.settings.timezone).date().isoformat()
    assert result["target_date"] == expected


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


def test_shadow_audit_rejects_future_target_date_before_touching_snapshots():
    svc = ShadowRunAuditService()
    future = datetime.now(svc.settings.timezone).date() + timedelta(days=1)
    with pytest.raises(ValueError, match="shadow_audit_future_target_date_not_allowed"):
        svc.run(None, target_date=future)


def test_shadow_audit_queries_exclude_records_generated_after_market_cutoff(tmp_path):
    """SQL predicates must constrain the publication/creation clock as well as as_of_date."""
    from datetime import date
    from types import SimpleNamespace
    from app.core.config import Settings

    class Rows:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

        def first(self):
            return self.rows[0] if self.rows else None

    class CaptureSession:
        def __init__(self):
            self.sql = []

        def scalars(self, statement):
            rendered = str(statement.compile(compile_kwargs={"literal_binds": True}))
            self.sql.append(rendered)
            if "FROM instruments" in rendered:
                return Rows([SimpleNamespace(id=111111, ts_code="510300.SH",
                    name="fixture", theme_l1=None)])
            if "FROM forecast_snapshots" in rendered:
                return Rows([SimpleNamespace(
                    as_of_date=date(2026, 10, 21), horizon=1,
                    model_version="fixture", config_hash="fixture",
                    calibration_status="not_calibrated", p_up=None,
                    q10=None, q90=None, terminal_price_q10=None,
                    terminal_price_q90=None, path_low_price_q50=None,
                    path_high_price_q50=None, corridor_position=None,
                    support_touch_probability=None,
                    resistance_touch_probability=None,
                )])
            if "FROM daily_bars" in rendered:
                return Rows([SimpleNamespace(
                    trade_date=date(2026, 10, 22), pre_close=9.,
                    open=10., close=10., low=9., high=11.,
                )])
            return Rows([])

        def add(self, _row):
            pass

        def flush(self):
            pass

    db = CaptureSession()
    settings = Settings(_env_file=None, market_provider="mock", reports_dir=tmp_path)
    result = ShadowRunAuditService(settings).run(
        db, run_id="shadow-cutoff-compiled-contract", target_date=date(2026, 10, 23)
    )
    assert result["summary"]["audited"] == 1
    forecast_sql = next(query for query in db.sql if "FROM forecast_snapshots" in query)
    indicator_sql = next(query for query in db.sql if "FROM indicator_snapshots" in query)
    signal_sql = next(query for query in db.sql if "FROM signal_snapshots" in query)
    for sql, table in (
        (forecast_sql, "forecast_snapshots"),
        (indicator_sql, "indicator_snapshots"),
    ):
        assert table + ".generated_at <=" in sql
        assert "2026-10-23 06:30:00" in sql  # Shanghai 14:30, UTC generation time
    assert "signal_snapshots.as_of_time <=" in signal_sql
    assert "2026-10-23 14:30:00" in signal_sql
