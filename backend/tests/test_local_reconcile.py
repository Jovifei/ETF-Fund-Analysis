import json
from datetime import date, datetime, timezone

from sqlalchemy import select

from app.workspace.local_reconcile import SHANGHAI, recent_base_days, reconcile_delivery, run_reconcile
from app.workspace.shadow_bundle import digest


def _seq(day: date, hour: int) -> int:
    return int(datetime(day.year, day.month, day.day, hour, tzinfo=SHANGHAI).timestamp() * 1000)


def _write(outbox, seq, universe, receipt=None):
    manifest = {"contract_version": "local-display-v2", "sequence": seq, "universe": universe}
    (outbox / f"bundle_{seq}.json").write_text(json.dumps({"manifest": manifest, "parts": {}}))
    if receipt is not None:
        payload = receipt(digest(manifest), seq)
        (outbox / f"bundle_{seq}.receipt.json").write_text(json.dumps(payload))
    return digest(manifest)


def test_delivery_states_and_session_filter(tmp_path):
    outbox = tmp_path / "outbox"; outbox.mkdir()
    day = date(2026, 10, 14)
    ok = lambda bid, seq: {"bundle_id": bid, "manifest_hash": bid, "status": "accepted", "sequence": seq,
                           "received_at": "2026-10-14T06:31:00+00:00"}
    _write(outbox, _seq(day, 14), ["510300.SH"], ok)
    _write(outbox, _seq(day, 15), ["510300.SH"], lambda bid, seq: {**ok(bid, seq), "manifest_hash": "0" * 64})
    _write(outbox, _seq(day, 16), ["510300.SH"])
    _write(outbox, _seq(date(2026, 10, 13), 14), ["510300.SH"], ok)  # other session ignored
    result = reconcile_delivery(outbox, day)
    assert result["counts"] == {"MATCHED": 1, "RECEIPT_MISMATCH": 1, "RECEIPT_MISSING": 1}
    assert result["latest_matched"]["sequence"] == _seq(day, 14)


def test_reconcile_outcomes_mature_or_pending_and_report_local(tmp_path, bootstrapped, db_session):
    from app.models import DailyBar, Instrument
    inst = db_session.scalars(select(Instrument)).first()
    days = sorted(db_session.scalars(select(DailyBar.trade_date).where(DailyBar.instrument_id == inst.id,
                                                                       DailyBar.adjust == "none")).all())
    assert len(days) > 8
    session = days[-1]
    outbox = tmp_path / "outbox"; outbox.mkdir()
    ok = lambda bid, seq: {"bundle_id": bid, "manifest_hash": bid, "status": "accepted", "sequence": seq,
                           "received_at": "2026-10-14T06:31:00+00:00"}
    _write(outbox, _seq(session, 14), [inst.ts_code], ok)
    bases = recent_base_days(db_session, session, 6)
    report = run_reconcile(tmp_path, session=session, db=db_session, outcome_base_days=bases)
    assert report["consumer_identity"]["state"] == "NOT_RUN"
    assert report["actionable"] is False and report["calibration"] == "not_calibrated"
    by_base = {o["base_trade_date"]: o["rows"][0] for o in report["outcomes"]}
    newest = by_base[session.isoformat()]
    assert newest["t1"]["state"] == "PENDING_OUTCOME" and newest["t5"]["state"] == "PENDING_OUTCOME"
    oldest = by_base[bases[0].isoformat()]
    assert oldest["t1"]["state"] == "MATURED"
    saved = json.loads((tmp_path / "receipts" / "reconcile" / f"reconcile_{session.isoformat()}.json").read_text())
    assert saved["delivery"]["counts"] == {"MATCHED": 1}


def test_reconcile_without_matched_bundle_has_no_outcomes(tmp_path):
    (tmp_path / "outbox").mkdir()
    report = run_reconcile(tmp_path, session=date(2026, 10, 14))
    assert report["delivery"]["counts"] == {} and report["outcomes"] == []


def test_board_only_local_refresh_runs_without_market_tasks(monkeypatch):
    from app.core.config import get_settings
    from app.services.task_service import TaskService
    from app.workspace.local_compute import compute_board_only

    seen = []

    def spy(self, db, task_name, **kwargs):
        # Wiring check only: never persist TaskRuns into the shared suite DB.
        seen.append(task_name)
        return {"status": "succeeded"}

    monkeypatch.setattr(TaskService, "run", spy)
    results = compute_board_only(get_settings())
    assert seen == ["refresh_decision_board"]
    assert results[0]["task_name"] == "refresh_decision_board"


def test_board_only_refuses_display_only_settings():
    import pytest
    from app.core.config import Settings
    from app.workspace.local_compute import compute_board_only
    with pytest.raises(ValueError):
        compute_board_only(Settings(_env_file=None, market_provider="mock", workspace_research_source="local_bundle"))
