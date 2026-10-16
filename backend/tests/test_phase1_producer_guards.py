"""Offline negative regressions for producer qualification and reconciliation."""
import importlib.util
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.workspace.local_compute import validate_provider_admission
from app.workspace.local_reconcile import SHANGHAI, reconcile_delivery, run_reconcile
from app.workspace.local_schedule import LocalRunLock
from app.workspace.shadow_bundle import digest

ROOT = Path(__file__).resolve().parents[2]


def load_cli(name="run_local_compute"):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def admission():
    return {
        "schema": "provider-admission-evidence-v1",
        "provider": "public_composite",
        "interfaces": [{
            "name": key,
            **{permission: {"status": "VERIFIED", "evidence_type": "upstream_terms_or_license",
                            "evidence_ref": "synthetic-test-only"} for permission in ("acquire", "store", "display")},
            "units": {"volume": "shares", "amount": "CNY", "return": "fraction", "evidence_ref": "synthetic-units"},
            "source_timestamp_quality": {"status": "VERIFIED", "evidence_ref": "synthetic-time"},
            "adjustment_basis": {"value": "qfq", "evidence_ref": "synthetic-basis"},
            "valid_until": "2099-01-01T00:00:00+00:00",
        } for key in ("daily_bars", "quotes", "sector_snapshots", "market_context")],
    }


def test_provider_name_does_not_grant_admission():
    result = validate_provider_admission("public_composite")
    assert result["admitted"] is False
    assert result["license_status"] == "UNKNOWN"
    assert result["source_timestamp_quality"] == "UNKNOWN"


@pytest.mark.parametrize("field", ["acquire", "store", "display", "units", "source_timestamp_quality", "adjustment_basis", "valid_until"])
def test_admission_requires_every_endpoint_and_dimension(field):
    evidence = admission()
    evidence["interfaces"][0].pop(field)
    assert validate_provider_admission("public_composite", evidence=evidence)["admitted"] is False


def test_explicit_bound_admission_and_wrong_provider():
    assert validate_provider_admission("public_composite", evidence=admission())["admitted"] is True
    assert validate_provider_admission("akshare", evidence=admission())["admitted"] is False


def test_active_old_lock_cannot_be_stolen(tmp_path):
    path = tmp_path / "run.lock"
    first, second = LocalRunLock(path), LocalRunLock(path)
    assert first.acquire()
    os.utime(path, (1, 1))
    try:
        assert not second.acquire()
    finally:
        first.release()


@pytest.mark.parametrize("missing", ["manifest_hash", "sequence", "status", "received_at"])
def test_reconcile_missing_receipt_fields_never_match(tmp_path, missing):
    seq = int(datetime(2026, 10, 14, 14, tzinfo=SHANGHAI).timestamp() * 1000)
    manifest = {"sequence": seq, "universe": ["510300.SH"], "contract_version": "local-display-v2"}
    (tmp_path / f"bundle_{seq}.json").write_text(json.dumps({"manifest": manifest}))
    receipt = {"bundle_id": digest(manifest), "manifest_hash": digest(manifest), "sequence": seq,
               "status": "accepted", "received_at": "2026-10-14T06:00:00+00:00"}
    receipt.pop(missing)
    (tmp_path / f"bundle_{seq}.receipt.json").write_text(json.dumps(receipt))
    assert reconcile_delivery(tmp_path, date(2026, 10, 14))["counts"] == {"RECEIPT_MISMATCH": 1}


def test_empty_reconcile_is_not_overall_pass(tmp_path):
    report = run_reconcile(tmp_path, session=date(2026, 10, 14))
    assert report["state"] == "INCOMPLETE"


def test_missing_config_rejected_before_compute(tmp_path, monkeypatch):
    cli = load_cli()
    seen = []
    monkeypatch.setattr(cli, "compute_local", lambda *a, **k: seen.append("computed") or [])
    monkeypatch.setattr(cli, "get_current_git_sha", lambda: "b" * 40)
    args = SimpleNamespace(root=str(tmp_path), db=None, profile="mock", provider="mock",
                           config=str(tmp_path / "missing.json"), skip_trade_day_check=True,
                           board_only=False, no_upload=True)
    with pytest.raises(ValueError, match="config"):
        cli.cmd_run(args)
    assert seen == [] and not (tmp_path / "outbox").exists()


def test_dirty_identity_rejected_before_compute(tmp_path, monkeypatch):
    cli = load_cli()
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"universe": ["510300.SH"]}))
    monkeypatch.setattr(cli, "get_current_git_sha", lambda: (_ for _ in ()).throw(RuntimeError("dirty")))
    seen = []
    monkeypatch.setattr(cli, "compute_local", lambda *a, **k: seen.append("computed") or [])
    args = SimpleNamespace(root=str(tmp_path), db=None, profile="mock", provider="mock", config=str(cfg),
                           skip_trade_day_check=True, board_only=False, no_upload=True)
    with pytest.raises(RuntimeError, match="dirty"):
        cli.cmd_run(args)
    assert seen == []


@pytest.mark.parametrize("failure", ["dirty", "mismatch", "missing_expected"])
def test_source_preflight_never_reads_config_for_rejected_identity(tmp_path, monkeypatch, failure):
    cli = load_cli()
    monkeypatch.setattr(cli, "read_execution", lambda *args: pytest.fail("rejected source must not read configuration"))
    if failure == "dirty":
        monkeypatch.setattr(cli, "get_current_git_sha", lambda: (_ for _ in ()).throw(RuntimeError("dirty")))
    else:
        monkeypatch.setattr(cli, "get_current_git_sha", lambda: "b" * 40)
    args = SimpleNamespace(root=str(tmp_path), config=None, profile="live", no_upload=False,
                           expected_sha=None if failure == "missing_expected" else "f" * 40)
    with pytest.raises(RuntimeError if failure == "dirty" else ValueError,
                       match="dirty" if failure == "dirty" else "identity|expected-sha"):
        cli.cmd_run(args)


@pytest.mark.parametrize("operation", ["read_bytes", "is_file"])
def test_unreadable_config_uses_safe_value_error_contract(tmp_path, monkeypatch, operation):
    cli = load_cli()
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"universe": ["510300.SH"]}))
    monkeypatch.setattr(type(config), operation, lambda self: (_ for _ in ()).throw(
        PermissionError("private details must not appear")))
    args = SimpleNamespace(root=str(tmp_path), db=None, profile="mock", provider="mock", config=str(config))
    with pytest.raises(ValueError, match="^local config file required$"):
        cli.read_execution(args)


def test_partial_compute_must_not_export(tmp_path, monkeypatch):
    cli = load_cli()
    (tmp_path / ".shadow-local").touch()
    db = tmp_path / "research.sqlite3"
    db.touch()
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"universe": ["510300.SH"]}))
    monkeypatch.setattr(cli, "get_current_git_sha", lambda: "b" * 40)
    monkeypatch.setattr(cli, "compute_local", lambda *a, **k: [{"status": "partial"}])
    monkeypatch.setattr(cli, "export_local_v2", lambda *a, **k: pytest.fail("partial must not export"))
    args = SimpleNamespace(root=str(tmp_path), db=str(db), profile="mock", provider="mock", config=str(cfg),
                           skip_trade_day_check=True, board_only=False, no_upload=True)
    assert cli.cmd_run(args) == 1
    assert not (tmp_path / "outbox").exists()


def test_bootstrap_dry_run_does_not_construct_task_service(tmp_path, monkeypatch):
    cli = load_cli("bootstrap_etf_history")
    (tmp_path / ".local-live").touch()
    db = tmp_path / "research.sqlite3"
    from sqlalchemy import create_engine
    from app.db.base import Base
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    Base.metadata.create_all(engine)
    engine.dispose()
    monkeypatch.setattr(cli, "TaskService", lambda *a, **k: pytest.fail("dry run must not fetch/write"))
    result = cli.bootstrap_universe(tmp_path, db, ["510300.SH"], dry_run=True)
    assert result["bootstrapped"] == []


def test_registration_never_force_overwrites_existing_task():
    content = (ROOT / "scripts/register_local_compute_task.ps1").read_text()
    assert "Get-ScheduledTask" in content
    assert " -Force" not in content


def test_local_compute_without_display_permission_does_not_grant_export():
    evidence = admission()
    for row in evidence["interfaces"]:
        row["display"] = {"status": "UNKNOWN"}
    assert validate_provider_admission("public_composite", evidence=evidence, purpose="compute")["admitted"]
    assert not validate_provider_admission("public_composite", evidence=evidence)["admitted"]


def test_owner_approval_alone_does_not_claim_upstream_license():
    evidence = admission()
    evidence["interfaces"][0]["display"]["evidence_ref"] = "owner-approval:synthetic"
    assert not validate_provider_admission("public_composite", evidence=evidence)["admitted"]


def test_atomic_write_failure_keeps_original_and_removes_temporary(tmp_path, monkeypatch):
    from app.workspace import local_atomic
    target = tmp_path / "bundle.json"
    target.write_text('{"original": true}')
    monkeypatch.setattr(local_atomic.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("synthetic_disk_failure")))
    with pytest.raises(OSError):
        local_atomic.write_json_atomic(target, {"new": True})
    assert json.loads(target.read_text()) == {"original": True}
    assert list(tmp_path.iterdir()) == [target]


@pytest.fixture
def outcome_db():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.db.base import Base
    from app.models import DailyBar, Instrument
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        instrument = Instrument(ts_code="510300.SH", symbol="510300", name="synthetic")
        db.add(instrument)
        db.flush()
        for day in (5, 6, 7):
            db.add(DailyBar(instrument_id=instrument.id, trade_date=date(2026, 1, day),
                open=10, high=12, low=9, close=10 + (day - 5), volume=1000,
                adjust="qfq", source="synthetic_real_adapter", quality_hash=str(day) * 64,
                fetched_at=datetime(2026, 1, 7, 9, tzinfo=timezone.utc)))
        db.commit()
        yield db
    engine.dispose()


class VerifiedWeekdays:
    def decision(self, day):
        return SimpleNamespace(verified=True, is_trade_day=day.weekday() < 5)


def _outcome(db, at, evidence=True):
    from app.workspace.local_reconcile import realised_outcomes
    proof = {"510300.SH": {"adjust": "qfq", "evidence_ref": "synthetic-same-vintage",
                           "settlement_status": "settled", "price_basis_id": "synthetic-qfq-generation-1",
                           "quality_hashes": [str(day) * 64 for day in (5, 6, 7)]}} if evidence else None
    return realised_outcomes(db, ["510300.SH"], date(2026, 1, 5), as_of=at,
                             calendar=VerifiedWeekdays(), price_evidence=proof)[0]


def test_outcome_uses_session_not_nth_stored_bar(outcome_db):
    from sqlalchemy import delete
    from app.models import DailyBar
    outcome_db.execute(delete(DailyBar).where(DailyBar.trade_date == date(2026, 1, 6)))
    outcome_db.commit()
    row = _outcome(outcome_db, datetime(2026, 1, 7, 10, tzinfo=timezone.utc))
    assert row["t1"]["state"] == "UNKNOWN"
    assert row["t5"]["state"] == "PENDING_OUTCOME"


def test_outcome_waits_for_settlement_cutoff(outcome_db):
    row = _outcome(outcome_db, datetime(2026, 1, 6, 6, tzinfo=timezone.utc))
    assert row["t1"]["state"] == "PENDING_OUTCOME"


def test_matured_outcome_requires_bound_comparable_non_mock_prices(outcome_db):
    cutoff = datetime(2026, 1, 7, 10, tzinfo=timezone.utc)
    row = _outcome(outcome_db, cutoff)
    assert row["t1"] == {"state": "MATURED", "trade_date": "2026-01-06", "return": 0.1}
    assert _outcome(outcome_db, cutoff, evidence=False)["t1"]["state"] == "UNKNOWN"
    from sqlalchemy import update
    from app.models import DailyBar
    outcome_db.execute(update(DailyBar).values(source="mock"))
    outcome_db.commit()
    assert _outcome(outcome_db, cutoff)["t1"]["state"] == "UNKNOWN"


def test_future_fetched_bar_not_used_even_if_session_already_elapsed(outcome_db):
    row = _outcome(outcome_db, datetime(2026, 1, 7, 8, tzinfo=timezone.utc))
    assert row["t1"]["state"] == "UNKNOWN"

