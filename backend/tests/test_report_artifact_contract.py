from __future__ import annotations

import json
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from app.core.config import get_settings
from app.core.security import hash_password
from app.models import AuthUser, ReportArtifact
from app.services.report_artifact_contract import (
    latest_system_report,
    read_system_json_report,
)
from app.utils.hashing import stable_hash
from app.workspace.read_model import factor_view


def _write_report(
    db_session,
    *,
    report_type: str,
    payload: dict,
    as_of_time: datetime,
    user_id: int | None = None,
    metadata: dict | None = None,
):
    settings = get_settings()
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    path = settings.reports_dir / f"{report_type}-{uuid4().hex}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    artifact = ReportArtifact(
        user_id=user_id,
        report_type=report_type,
        as_of_time=as_of_time,
        file_path=str(path),
        content_hash=stable_hash(payload),
        metadata_json=metadata or {},
    )
    db_session.add(artifact)
    db_session.flush()
    return artifact, path


def test_latest_system_report_uses_append_order_and_ignores_user_owned(db_session):
    base = datetime(2026, 10, 4, 8, 0, 0)
    old, _ = _write_report(
        db_session,
        report_type="factor_effectiveness",
        payload={"report_type": "factor_effectiveness", "marker": "older"},
        as_of_time=base + timedelta(hours=8),
    )
    newer, _ = _write_report(
        db_session,
        report_type="factor_effectiveness",
        payload={"report_type": "factor_effectiveness", "marker": "newer"},
        as_of_time=base,
    )
    user = AuthUser(
        username=f"artifact-{uuid4().hex}",
        password_hash=hash_password("artifact test password"),
        role="member",
        status="active",
    )
    db_session.add(user)
    db_session.flush()
    private, _ = _write_report(
        db_session,
        report_type="factor_effectiveness",
        payload={"report_type": "factor_effectiveness", "marker": "private"},
        as_of_time=base + timedelta(days=1),
        user_id=user.id,
    )

    selected = latest_system_report(db_session, "factor_effectiveness")
    assert selected is not None
    assert selected.id == newer.id
    assert selected.id > old.id
    assert private.id > selected.id
    db_session.rollback()


def test_system_json_reader_rejects_path_escape_tamper_type_and_user_owned(db_session, tmp_path):
    settings = get_settings()
    now = datetime(2026, 10, 4, 8, 0, 0)
    payload = {"report_type": "factor_effectiveness", "marker": "ok"}
    artifact, path = _write_report(
        db_session,
        report_type="factor_effectiveness",
        payload=payload,
        as_of_time=now,
    )
    assert read_system_json_report(
        artifact, settings, expected_type="factor_effectiveness"
    )["marker"] == "ok"

    path.write_text(
        json.dumps({"report_type": "factor_effectiveness", "marker": "tampered"}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="content hash"):
        read_system_json_report(artifact, settings, expected_type="factor_effectiveness")

    escape_payload = {"report_type": "factor_effectiveness", "marker": "escape"}
    escape_path = tmp_path / "escape.json"
    escape_path.write_text(json.dumps(escape_payload), encoding="utf-8")
    escape_artifact = ReportArtifact(
        report_type="factor_effectiveness",
        as_of_time=now,
        file_path=str(escape_path),
        content_hash=stable_hash(escape_payload),
        metadata_json={},
    )
    db_session.add(escape_artifact)
    db_session.flush()
    with pytest.raises(ValueError):
        read_system_json_report(
            escape_artifact, settings, expected_type="factor_effectiveness"
        )

    wrong_payload = {"report_type": "other", "marker": "wrong-type"}
    wrong, _ = _write_report(
        db_session,
        report_type="factor_effectiveness",
        payload=wrong_payload,
        as_of_time=now,
    )
    with pytest.raises(ValueError, match="type mismatch"):
        read_system_json_report(wrong, settings, expected_type="factor_effectiveness")

    user = AuthUser(
        username=f"artifact-reader-{uuid4().hex}",
        password_hash=hash_password("artifact test password"),
        role="member",
        status="active",
    )
    db_session.add(user)
    db_session.flush()
    private_payload = {"report_type": "factor_effectiveness", "marker": "private"}
    private, _ = _write_report(
        db_session,
        report_type="factor_effectiveness",
        payload=private_payload,
        as_of_time=now,
        user_id=user.id,
    )
    with pytest.raises(ValueError, match="user_owned"):
        read_system_json_report(private, settings, expected_type="factor_effectiveness")
    db_session.rollback()


def _factor_payload(settings, *, analysis_version: str | None = None):
    strategy = settings.load_strategy()
    research_contract = {
        "policy": "canonical_research_history_v1",
        "basis_by_instrument": {},
        "excluded": [],
    }
    universe_contract = {
        "version": "research-universe-v1-current-enabled",
        "selection": "current_enabled_snapshot",
        "survivorship_bias_controlled": False,
        "qualification": "UNKNOWN",
    }
    payload = {
        "report_type": "factor_effectiveness",
        "analysis_version": analysis_version or strategy["factor_analysis"]["version"],
        "feature_schema_version": strategy["feature_schema_version"],
        "qualification": "UNKNOWN",
        "panel": {
            "research_input_contract": research_contract,
            "universe_contract": universe_contract,
        },
    }
    metadata = {
        "research_input_contract_hash": stable_hash(research_contract),
        "universe_contract_hash": stable_hash(universe_contract),
    }
    return payload, metadata


def test_factor_view_uses_latest_append_and_rejects_incompatible_report(db_session):
    settings = get_settings()
    base = datetime(2026, 10, 4, 8, 0, 0)

    current_payload, current_meta = _factor_payload(settings)
    old, _ = _write_report(
        db_session,
        report_type="factor_effectiveness",
        payload=current_payload,
        metadata=current_meta,
        as_of_time=base + timedelta(hours=8),
    )

    incompatible_payload, incompatible_meta = _factor_payload(
        settings, analysis_version="factor-analysis-stale"
    )
    newer, _ = _write_report(
        db_session,
        report_type="factor_effectiveness",
        payload=incompatible_payload,
        metadata=incompatible_meta,
        as_of_time=base,
    )
    view = factor_view(db_session, settings)
    assert newer.id > old.id
    assert view["report_artifact_id"] == newer.id
    assert view["report"] is None
    assert view["report_state"] == "incompatible"
    assert "analysis_version_mismatch" in view["report_reason"]

    final_payload, final_meta = _factor_payload(settings)
    final, _ = _write_report(
        db_session,
        report_type="factor_effectiveness",
        payload=final_payload,
        metadata=final_meta,
        as_of_time=base - timedelta(hours=1),
    )
    view = factor_view(db_session, settings)
    assert view["report_artifact_id"] == final.id
    assert view["report_state"] == "current"
    assert view["report_reason"] is None
    assert view["report"]["analysis_version"] == settings.load_strategy()["factor_analysis"]["version"]
    assert view["actionable"] is False
    db_session.rollback()
