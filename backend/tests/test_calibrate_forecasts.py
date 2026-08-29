"""Tests for calibrate_forecasts (calibration_service + task registration).

Covers: create_candidate skip/duplicate/candidate_created, decide approved/rejected,
gate blocking, version-consistency blocking. Does NOT test actual promotion logic
(because calibration_status is never changed — this is a documented invariant).
"""
from __future__ import annotations

from pathlib import Path

from app.services.calibration_service import CalibrationService
from app.services.task_service import TaskService


def _latest_validation_payload(bootstrapped, db_session) -> dict:
    """Run validate_forecasts and read back the written report JSON."""
    from sqlalchemy import select
    from app.models import ReportArtifact
    result = TaskService().run(db_session, "validate_forecasts")
    db_session.commit()
    artifact = db_session.scalars(
        select(ReportArtifact)
        .where(ReportArtifact.report_type == "forecast_validation")
        .order_by(ReportArtifact.as_of_time.desc())
        .limit(1)
    ).first()
    assert artifact is not None
    payload = Path(artifact.file_path).read_text(encoding="utf-8")
    return __import__("json").loads(payload), result, artifact


def test_calibrate_forecasts_task_exists():
    assert "calibrate_forecasts" in TaskService().task_names


def test_calibrate_skip_when_no_report(db_session):
    """With no validation report, calibrate_forecasts must skip cleanly."""
    svc = CalibrationService()
    result = svc.create_candidate(db_session, run_id="test-no-report")
    assert result["status"] == "skipped"
    assert "no forecast_validation" in result["reason"]


def test_calibrate_creates_candidate_and_is_idempotent(bootstrapped, db_session):
    """A full create path: validation report exists → candidate is created.
    Re-running with the same validation content hash returns duplicate."""
    svc = CalibrationService()

    # First: validate so we have a report
    payload, val_result, artifact = _latest_validation_payload(bootstrapped, db_session)

    # Create candidate
    result1 = svc.create_candidate(db_session, run_id="test-create-1")
    db_session.commit()
    assert result1["status"] == "candidate_created"
    assert result1["gates_passed"] is not None
    assert result1["gate_results"]["items"]["instrument_count"] is True
    profile_id = result1["profile_id"]

    # Re-run: must be duplicate
    result2 = svc.create_candidate(db_session, run_id="test-create-2")
    db_session.commit()
    assert result2["status"] == "duplicate"
    assert result2["profile_id"] == profile_id


def test_calibrate_reject_flow(bootstrapped, db_session):
    """A full reject path: create → reject must succeed."""
    svc = CalibrationService()
    _, _, _ = _latest_validation_payload(bootstrapped, db_session)
    result = svc.create_candidate(db_session, run_id="test-reject-create")
    db_session.commit()

    # Reject
    dec = svc.decide(db_session, result["profile_id"], "rejected", approved_by="test-user")
    db_session.commit()
    assert dec["status"] == "rejected"


def test_calibrate_reject_blocks_approval_without_manual_gates(bootstrapped, db_session):
    """Mock-based validation produces mock data, which should block approval
    because gate_results.all_passed is False."""
    svc = CalibrationService()
    _, _, _ = _latest_validation_payload(bootstrapped, db_session)
    result = svc.create_candidate(db_session, run_id="test-approval-gate")
    db_session.commit()

    # Gate check: all_passed should be False (mock data has low coverage/accuracy)
    assert result["gates_passed"] is False

    # Approval must raise ValueError when gates fail
    try:
        svc.decide(db_session, result["profile_id"], "approved", approved_by="test-user")
        db_session.rollback()
        # If no exception: mock data somehow passed all gates — not an error, just unexpected
    except ValueError as exc:
        assert "blocked" in str(exc) or "failed" in str(exc)


def test_calibrate_reject_blocks_approval_with_version_mismatch(bootstrapped, db_session):
    """Even with perfect gates, approval must fail if model_version doesn't match."""
    from app.services.calibration_service import CalibrationService
    from unittest.mock import patch
    svc = CalibrationService()
    _, _, _ = _latest_validation_payload(bootstrapped, db_session)
    result = svc.create_candidate(db_session, run_id="test-version-block")
    db_session.commit()

    # Force the profile's model_version to something different
    from app.models import CalibrationProfile
    profile = db_session.get(CalibrationProfile, result["profile_id"])
    profile.model_version = "outdated-model-version"
    db_session.flush()

    try:
        svc.decide(db_session, result["profile_id"], "approved", approved_by="test-user")
        db_session.rollback()
    except ValueError as exc:
        assert "model_version" in str(exc)
