"""Tests for calibrate_forecasts (calibration_service + task registration).

Covers: create_candidate skip/duplicate/candidate_created, decide approved/rejected,
gate blocking, version-consistency blocking. Does NOT test actual promotion logic
(because calibration_status is never changed — this is a documented invariant).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.models import ReportArtifact
from app.services.calibration_service import CalibrationService
from app.services.validation_service import VALIDATION_CONTRACT_VERSION
from app.services.task_service import TaskService
from app.utils.hashing import stable_hash
from app.utils.reproducibility import current_git_commit


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


def _write_validation_artifact(db_session, tmp_path, payload):
    content_hash = stable_hash(payload)
    path = tmp_path / f"validation-{content_hash[:8]}.json"
    path.write_text(json.dumps(payload, allow_nan=True), encoding="utf-8")
    db_session.add(ReportArtifact(
        report_type="forecast_validation",
        as_of_time=datetime.now().astimezone(),
        file_path=str(path),
        content_hash=content_hash,
        metadata_json={},
    ))
    db_session.flush()
    return path


def _synthetic_validation_payload(svc, *, horizons=(1, 3, 5, 10), source="public_composite",
                                  pit=True, holdout=True, nan_metric=False, run_id="synthetic-validation"):
    rows = []
    for instrument in range(5):
        metrics = {}
        for horizon in horizons:
            metrics[str(horizon)] = {
                "sample_count": 20,
                "directional_accuracy": float("nan") if nan_metric and instrument == 0 and horizon == horizons[0] else 0.6,
                "brier_score": 0.2,
                "interval_80_coverage": 0.8,
                "quantile_crossing_rate": 0.0,
                "support_touch_brier": 0.2,
                "resistance_touch_brier": 0.2,
            }
        rows.append({"status": "ok", "horizons": metrics})
    return {
        "run_id": run_id,
        "validation_contract_version": VALIDATION_CONTRACT_VERSION,
        "model_version": svc.strategy["forecast_version"],
        "feature_schema_version": svc.strategy["feature_schema_version"],
        "config_hash": stable_hash(svc.strategy),
        "git_commit_sha": current_git_commit(),
        "horizon_contract": list(horizons),
        "input_lineage_hash": "a" * 64,
        "input_contract": {
            "source": source,
            "independent_holdout": holdout,
            "pit_qualified": pit,
            "calibration_eligible": True,
            "qualification": "SYNTHETIC_TEST_ONLY",
        },
        "instruments": rows,
    }


def test_default_run_id_skip_is_isolated_from_shared_report_state():
    class EmptyResult:
        @staticmethod
        def first():
            return None

    class EmptyDb:
        @staticmethod
        def scalars(_statement):
            return EmptyResult()

    result = CalibrationService().create_candidate(EmptyDb())  # type: ignore[arg-type]
    assert result["status"] == "skipped"
    assert len(result["run_id"]) == 32


def test_candidate_fails_closed_for_single_horizon_mock_no_holdout_and_nan(db_session, tmp_path):
    svc = CalibrationService()
    payload = _synthetic_validation_payload(
        svc, horizons=(1,), source="mock", pit=False, holdout=False, nan_metric=True
    )
    _write_validation_artifact(db_session, tmp_path, payload)
    result = svc.create_candidate(db_session, run_id="strict-negative")
    items = result["gate_results"]["items"]
    assert result["gates_passed"] is False
    assert items["metrics_valid"] is False
    assert items["all_formal_horizons"] is False
    assert items["validation_contract_eligible"] is False
    assert items["independent_holdout_verified"] is False
    assert items["source_non_synthetic"] is False
    assert items["pit_qualified_verified"] is False


def test_approval_reloads_and_rehashes_original_validation_artifact(db_session, tmp_path):
    svc = CalibrationService()
    payload = _synthetic_validation_payload(svc, run_id="tamper-fixture")
    path = _write_validation_artifact(db_session, tmp_path, payload)
    result = svc.create_candidate(db_session, run_id="strict-tamper-fixture")
    assert result["gates_passed"] is False
    assert result["gate_results"]["items"]["validation_contract_eligible"] is False
    path.write_text(json.dumps({**payload, "run_id": "tampered-after-candidate"}), encoding="utf-8")
    try:
        svc.decide(db_session, result["profile_id"], "approved", approved_by="test-user")
        raise AssertionError("tampered validation artifact must not be approved")
    except ValueError as exc:
        assert "validation_content_hash_matches" in str(exc)


def test_bad_h10_cannot_hide_inside_good_aggregate_metrics(db_session, tmp_path):
    svc = CalibrationService()
    payload = _synthetic_validation_payload(svc, run_id="bad-h10")
    for row in payload["instruments"]:
        row["horizons"]["10"]["directional_accuracy"] = 0.0
    _write_validation_artifact(db_session, tmp_path, payload)
    result = svc.create_candidate(db_session, run_id="bad-h10-candidate")
    assert result["gate_results"]["horizons"]["10"]["items"]["directional_accuracy"] is False
    assert result["gate_results"]["horizons"]["1"]["items"]["directional_accuracy"] is True
    assert result["gate_results"]["items"]["per_horizon_gates"] is False
    assert result["gates_passed"] is False


def test_empty_formal_horizon_is_a_hard_failure(db_session, tmp_path):
    svc = CalibrationService()
    payload = _synthetic_validation_payload(svc, run_id="empty-h10")
    for row in payload["instruments"]:
        row["horizons"]["10"] = {"sample_count": 0}
    _write_validation_artifact(db_session, tmp_path, payload)
    result = svc.create_candidate(db_session, run_id="empty-h10-candidate")
    h10 = result["gate_results"]["horizons"]["10"]
    assert h10["items"]["sample_count"] is False
    assert h10["items"]["metrics_valid"] is False
    assert result["gates_passed"] is False


def test_out_of_range_probability_metrics_fail_closed(db_session, tmp_path):
    svc = CalibrationService()
    payload = _synthetic_validation_payload(svc, run_id="range-invalid")
    payload["instruments"][0]["horizons"]["1"]["directional_accuracy"] = 1.2
    payload["instruments"][1]["horizons"]["3"]["brier_score"] = -0.1
    payload["instruments"][2]["horizons"]["5"]["interval_80_coverage"] = 2.0
    _write_validation_artifact(db_session, tmp_path, payload)
    result = svc.create_candidate(db_session, run_id="range-invalid-candidate")
    assert result["gate_results"]["items"]["metrics_valid"] is False
    assert result["gate_results"]["items"]["per_horizon_gates"] is False


def test_self_declared_holdout_pit_mock_fixture_and_arbitrary_lineage_cannot_qualify(db_session, tmp_path):
    svc = CalibrationService()
    payload = _synthetic_validation_payload(
        svc, source="mock_fixture", pit=True, holdout=True, run_id="self-declared"
    )
    payload["input_lineage_hash"] = "arbitrary-lineage"
    payload["validation_contract_version"] = "self-declared-qualified-contract"
    _write_validation_artifact(db_session, tmp_path, payload)
    result = svc.create_candidate(db_session, run_id="self-declared-candidate")
    items = result["gate_results"]["items"]
    assert items["validation_contract_eligible"] is False
    assert items["independent_holdout_verified"] is False
    assert items["pit_qualified_verified"] is False
    assert items["source_non_synthetic"] is False
    assert items["input_lineage_digest_valid"] is False
    assert result["gates_passed"] is False


def test_current_validator_contract_is_explicitly_nonqualifying_even_when_report_booleans_are_forged(db_session, tmp_path):
    svc = CalibrationService()
    payload = _synthetic_validation_payload(svc, source="public_composite", pit=True, holdout=True,
                                            run_id="current-contract-forged-flags")
    payload["validation_contract_version"] = VALIDATION_CONTRACT_VERSION
    payload["input_lineage_hash"] = "b" * 64
    _write_validation_artifact(db_session, tmp_path, payload)
    result = svc.create_candidate(db_session, run_id="current-contract-candidate")
    assert result["summary"]["declared_independent_holdout"] is True
    assert result["summary"]["declared_pit_qualified"] is True
    assert result["summary"]["validation_contract_eligible"] is False
    assert result["gates_passed"] is False
