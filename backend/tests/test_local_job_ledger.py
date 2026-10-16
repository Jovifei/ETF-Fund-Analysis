from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.workspace.local_job_ledger import LocalJobLedger
from app.workspace.shadow_bundle import digest

ZONE = ZoneInfo("Asia/Shanghai")
IDENTITY = {"code_sha": "a" * 40, "config_hash": "b" * 64, "scope_hash": digest(["510300.SH"])}


def now(hour=14, minute=50, day=16):
    return datetime(2026, 10, day, hour, minute, tzinfo=ZONE)


def claim(ledger, when=None):
    when = when or now()
    due = ledger.plan_due(when, verified_trading=True, identity=IDENTITY)
    return ledger.claim(due["slot_id"], when, identity=IDENTITY, lock_held=True)


def packet(when):
    return {"contract_version": "local-display-v2", "sequence": 123,
            "code_sha": IDENTITY["code_sha"], "config_hash": IDENTITY["config_hash"],
            "universe": ["510300.SH"],
            "expires_at": (when + timedelta(minutes=20)).isoformat()}


def receipt(manifest):
    bid = digest(manifest)
    return {"bundle_id": bid, "manifest_hash": bid, "sequence": 123,
            "status": "accepted", "received_at": now().isoformat()}


def test_latest_due_supersedes_old_slots_and_persists(tmp_path):
    ledger = LocalJobLedger(tmp_path)
    due = ledger.plan_due(now(14, 51), verified_trading=True, identity=IDENTITY)
    assert due["slot"] == "14:50"
    assert LocalJobLedger(tmp_path).get_slot(due["slot_id"])["status"] == "PENDING"
    assert ledger.get_slot(due["slot_id"])["planned_at"] == "2026-10-16T06:50:00+00:00"
    states = {row["slot"]: row["status"] for row in ledger.summary()["slots"]}
    assert states["14:45"] == "SUPERSEDED" and states["14:55"] == "PENDING"


def test_claim_requires_lock_and_preserves_interrupted_attempt(tmp_path):
    ledger = LocalJobLedger(tmp_path)
    due = ledger.plan_due(now(), verified_trading=True, identity=IDENTITY)
    with pytest.raises(ValueError, match="lock"):
        ledger.claim(due["slot_id"], now(), identity=IDENTITY, lock_held=False)
    attempt = claim(ledger)
    assert ledger.recover_interrupted(now(), lock_held=True) == 1
    assert ledger.get_attempt(attempt["attempt_id"])["status"] == "INTERRUPTED"
    assert ledger.plan_due(now(), verified_trading=True, identity=IDENTITY) is None
    retry = ledger.plan_due(now() + timedelta(seconds=61), verified_trading=True, identity=IDENTITY)
    again = ledger.claim(retry["slot_id"], now() + timedelta(seconds=61), identity=IDENTITY, lock_held=True)
    assert again["attempt_no"] == 2
    ledger.fail(again["attempt_id"], reason="ProviderError", now=now() + timedelta(seconds=62))
    assert ledger.plan_due(now() + timedelta(seconds=123), verified_trading=True, identity=IDENTITY) is None
    assert len(ledger.summary()["attempts"]) == 2


def test_delivery_is_idempotent_and_never_implied_by_export(tmp_path):
    ledger = LocalJobLedger(tmp_path)
    attempt = claim(ledger)
    aid = attempt["attempt_id"]
    ledger.record_job(aid, "refresh_quotes", status="succeeded", now=now(), run_id="task-1")
    manifest = packet(now())
    ledger.mark_export(aid, manifest=manifest, bundle_file="bundle_123.json", now=now())
    assert ledger.pending_replay(now=now(), identity=IDENTITY)["attempt_id"] == aid
    assert ledger.get_slot(attempt["slot_id"])["status"] == "EXPORTED"
    bad = {**receipt(manifest), "sequence": 124}
    with pytest.raises(ValueError):
        ledger.mark_delivered(aid, manifest=manifest, receipt=bad, now=now())
    ledger.mark_delivered(aid, manifest=manifest, receipt=receipt(manifest), now=now())
    ledger.mark_delivered(aid, manifest=manifest, receipt=receipt(manifest), now=now())
    assert ledger.pending_replay(now=now(), identity=IDENTITY) is None
    assert ledger.summary()["consumer_identity"]["state"] == "NOT_RUN"
    with pytest.raises(ValueError):
        ledger.fail(aid, reason="late failure", now=now())


def test_replay_requires_exact_identity_and_unexpired_bundle(tmp_path):
    ledger = LocalJobLedger(tmp_path)
    attempt = claim(ledger)
    ledger.mark_export(attempt["attempt_id"], manifest=packet(now()), bundle_file="bundle_123.json", now=now())
    assert ledger.pending_replay(now=now(), identity={**IDENTITY, "code_sha": "d" * 40}) is None
    assert ledger.pending_replay(now=now() + timedelta(minutes=21), identity=IDENTITY) is None


def test_upload_retry_budget_and_cooldown_are_persistent(tmp_path):
    ledger = LocalJobLedger(tmp_path)
    aid = claim(ledger)["attempt_id"]
    ledger.mark_export(aid, manifest=packet(now()), bundle_file="bundle_123.json", now=now())
    ledger.record_job(aid, "upload_1", status="failed", now=now())
    assert ledger.pending_replay(now=now(), identity=IDENTITY) is None
    assert ledger.pending_replay(now=now() + timedelta(seconds=61), identity=IDENTITY)
    ledger.record_job(aid, "upload_2", status="failed", now=now() + timedelta(seconds=61))
    assert ledger.pending_replay(now=now() + timedelta(seconds=122), identity=IDENTITY)
    ledger.record_job(aid, "upload_3", status="failed", now=now() + timedelta(seconds=122))
    assert ledger.pending_replay(now=now() + timedelta(seconds=183), identity=IDENTITY) is None
    assert len(LocalJobLedger(tmp_path).summary()["jobs"]) == 3


def test_expired_and_wrong_identity_exports_do_not_deadlock_slot(tmp_path):
    ledger = LocalJobLedger(tmp_path)
    aid = claim(ledger)["attempt_id"]
    ledger.mark_export(aid, manifest=packet(now()), bundle_file="bundle_123.json", now=now())
    newer = {**IDENTITY, "code_sha": "d" * 40}
    due = ledger.plan_due(now() + timedelta(seconds=61), verified_trading=True, identity=newer)
    assert due["slot"] == "14:50"
    assert ledger.get_attempt(aid)["status"] == "INVALIDATED"
    retry = ledger.claim(due["slot_id"], now() + timedelta(seconds=61), identity=newer, lock_held=True)
    manifest = {**packet(now()), "code_sha": newer["code_sha"], "expires_at": (now() + timedelta(seconds=90)).isoformat()}
    ledger.mark_export(retry["attempt_id"], manifest=manifest, bundle_file="bundle_123.json", now=now() + timedelta(seconds=61))
    ledger.plan_due(now() + timedelta(seconds=151), verified_trading=True, identity=newer)
    assert ledger.get_attempt(retry["attempt_id"])["status"] == "EXPIRED"


def test_claim_rejects_future_or_previous_session(tmp_path):
    ledger = LocalJobLedger(tmp_path)
    ledger.plan_due(now(), verified_trading=True, identity=IDENTITY)
    with pytest.raises(ValueError):
        ledger.claim("2026-10-16 14:55", now(), identity=IDENTITY, lock_held=True)
    with pytest.raises(ValueError):
        ledger.claim("2026-10-16 14:50", now(day=19), identity=IDENTITY, lock_held=True)


def test_private_details_are_rejected(tmp_path):
    ledger = LocalJobLedger(tmp_path)
    aid = claim(ledger)["attempt_id"]
    with pytest.raises(ValueError):
        ledger.record_job(aid, "upload", status="failed", now=now(), details={"token": "secret"})


def test_superseded_export_never_replayed(tmp_path):
    ledger = LocalJobLedger(tmp_path)
    aid = claim(ledger)["attempt_id"]
    ledger.mark_export(aid, manifest=packet(now()), bundle_file="bundle_123.json", now=now())
    due = ledger.plan_due(now(14, 55), verified_trading=True, identity=IDENTITY)
    assert due["slot"] == "14:55"
    assert ledger.get_slot("2026-10-16 14:50")["status"] == "SUPERSEDED"
    assert ledger.pending_replay(now=now(14, 55), identity=IDENTITY) is None


def test_state_symlink_cannot_redirect_ledger(tmp_path):
    target = tmp_path / "elsewhere"
    target.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    try:
        (root / "state").symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlink privilege unavailable")
    with pytest.raises(ValueError, match="symlink"):
        LocalJobLedger(root)
    assert not (target / "schedule.sqlite3").exists()


def test_symlink_detection_runs_before_sqlite_creation(tmp_path, monkeypatch):
    from pathlib import Path
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda p: p.name == "state" or original(p))
    with pytest.raises(ValueError, match="symlink"):
        LocalJobLedger(tmp_path)
    assert not (tmp_path / "state").exists()


def test_crash_preserves_packet_but_interrupts_upload_job(tmp_path):
    ledger = LocalJobLedger(tmp_path)
    aid = claim(ledger)["attempt_id"]
    ledger.mark_export(aid, manifest=packet(now()), bundle_file="bundle_123.json", now=now())
    ledger.record_job(aid, "upload_1", status="running", now=now())
    assert ledger.pending_replay(now=now(), identity=IDENTITY) is None
    assert ledger.recover_interrupted(now(), lock_held=True) == 0
    assert ledger.get_attempt(aid)["status"] == "EXPORTED"
    assert ledger.summary()["jobs"][0]["status"] == "interrupted"
    assert ledger.pending_replay(now=now() + timedelta(seconds=61), identity=IDENTITY)


def test_fail_finishes_running_job_but_keeps_prior_job_result(tmp_path):
    ledger = LocalJobLedger(tmp_path)
    aid = claim(ledger)["attempt_id"]
    ledger.record_job(aid, "refresh_bars", status="succeeded", now=now())
    ledger.record_job(aid, "refresh_quotes", status="running", now=now())
    ledger.fail(aid, reason="ProviderError", now=now() + timedelta(seconds=1))
    jobs = {row["job_name"]: row for row in ledger.summary()["jobs"]}
    assert jobs["refresh_bars"]["status"] == "succeeded"
    assert jobs["refresh_quotes"]["status"] == "failed"
    assert jobs["refresh_quotes"]["finished_at"] is not None


def test_clock_rollback_does_not_rewrite_attempt_timestamps(tmp_path):
    ledger = LocalJobLedger(tmp_path)
    aid = claim(ledger)["attempt_id"]
    with pytest.raises(ValueError, match="clock"):
        ledger.fail(aid, reason="ProviderError", now=now() - timedelta(seconds=1))
    assert ledger.get_attempt(aid)["status"] == "RUNNING"


def test_delivery_atomically_finishes_upload_job_before_callback_can_crash(tmp_path):
    ledger = LocalJobLedger(tmp_path)
    aid = claim(ledger)["attempt_id"]
    manifest = packet(now())
    ledger.mark_export(aid, manifest=manifest, bundle_file="bundle_123.json", now=now())
    ledger.record_job(aid, "upload_1", status="running", now=now())
    ledger.mark_delivered(aid, manifest=manifest, receipt=receipt(manifest), now=now() + timedelta(seconds=1))
    reopened = LocalJobLedger(tmp_path)
    job = reopened.summary()["jobs"][0]
    assert job["status"] == "succeeded" and job["finished_at"] is not None
    reopened.record_job(aid, "upload_1", status="succeeded", now=now() + timedelta(seconds=2))
    assert reopened.summary()["jobs"][0] == job


def test_clock_rollback_cannot_reactivate_expired_export_or_claim_old_slot(tmp_path):
    ledger = LocalJobLedger(tmp_path)
    attempt = claim(ledger)
    aid = attempt["attempt_id"]
    manifest = packet(now())
    ledger.mark_export(aid, manifest=manifest, bundle_file="bundle_123.json", now=now())
    assert ledger.pending_replay(now=now() + timedelta(minutes=21), identity=IDENTITY) is None
    before = ledger.summary()
    with pytest.raises(ValueError, match="clock"):
        ledger.pending_replay(now=now(), identity=IDENTITY)
    with pytest.raises(ValueError, match="clock"):
        ledger.plan_due(now(), verified_trading=True, identity=IDENTITY)
    with pytest.raises(ValueError, match="clock"):
        ledger.claim("2026-10-16 14:55", now(14, 55), identity=IDENTITY, lock_held=True)
    assert ledger.summary() == before


def test_long_manifest_ttl_does_not_extend_delivery_slot_window(tmp_path):
    ledger = LocalJobLedger(tmp_path)
    aid = claim(ledger)["attempt_id"]
    manifest = {**packet(now()), "expires_at": (now() + timedelta(hours=2)).isoformat()}
    ledger.mark_export(aid, manifest=manifest, bundle_file="bundle_123.json", now=now())
    assert ledger.pending_replay(now=now() + timedelta(minutes=21), identity=IDENTITY) is None
    assert ledger.get_attempt(aid)["status"] == "EXPIRED"
    assert ledger.get_slot("2026-10-16 14:50")["status"] == "MISSED"


def test_plan_due_expires_export_after_window_without_recomputation(tmp_path):
    ledger = LocalJobLedger(tmp_path)
    when = now(16, 10)
    aid = claim(ledger, when)["attempt_id"]
    manifest = {**packet(when), "expires_at": (when + timedelta(hours=2)).isoformat()}
    ledger.mark_export(aid, manifest=manifest, bundle_file="bundle_123.json", now=when)
    assert ledger.plan_due(when + timedelta(minutes=21), verified_trading=True, identity=IDENTITY) is None
    assert ledger.get_attempt(aid)["status"] == "EXPIRED"
    assert ledger.get_slot("2026-10-16 16:10")["status"] == "MISSED"


def test_upload_exhaustion_is_terminal_and_never_creates_new_sequence(tmp_path):
    ledger = LocalJobLedger(tmp_path)
    aid = claim(ledger)["attempt_id"]
    ledger.mark_export(aid, manifest=packet(now()), bundle_file="bundle_123.json", now=now())
    for number in range(1, 4):
        ledger.record_job(aid, f"upload_{number}", status="failed", now=now() + timedelta(seconds=number))
    assert ledger.pending_replay(now=now() + timedelta(seconds=64), identity=IDENTITY) is None
    attempt = ledger.get_attempt(aid)
    assert attempt["status"] == "FAILED_DELIVERY" and attempt["reason"] == "upload_retry_budget_exhausted"
    assert attempt["sequence"] == 123 and attempt["bundle_file"] == "bundle_123.json"
    assert ledger.plan_due(now() + timedelta(seconds=65), verified_trading=True, identity=IDENTITY) is None
    with pytest.raises(ValueError):
        ledger.claim("2026-10-16 14:50", now() + timedelta(seconds=65), identity=IDENTITY, lock_held=True)
    ledger.plan_due(now(14, 55), verified_trading=True, identity=IDENTITY)
    assert ledger.get_slot("2026-10-16 14:50")["status"] == "FAILED_DELIVERY"


def test_previous_session_export_never_replayed_even_with_long_ttl(tmp_path):
    ledger = LocalJobLedger(tmp_path)
    aid = claim(ledger)["attempt_id"]
    manifest = {**packet(now()), "expires_at": (now() + timedelta(days=4)).isoformat()}
    ledger.mark_export(aid, manifest=manifest, bundle_file="bundle_123.json", now=now())
    assert ledger.pending_replay(now=now(day=19), identity=IDENTITY) is None
    assert ledger.get_slot("2026-10-16 14:50")["status"] == "MISSED"


def test_new_slot_does_not_hide_exhausted_delivery_budget(tmp_path):
    ledger = LocalJobLedger(tmp_path)
    aid = claim(ledger)["attempt_id"]
    ledger.mark_export(aid, manifest=packet(now()), bundle_file="bundle_123.json", now=now())
    for number in range(1, 4):
        ledger.record_job(aid, f"upload_{number}", status="failed", now=now() + timedelta(seconds=number))
    assert ledger.plan_due(now(14, 55), verified_trading=True, identity=IDENTITY)["slot"] == "14:55"
    assert ledger.get_slot("2026-10-16 14:50")["status"] == "FAILED_DELIVERY"
    assert ledger.get_attempt(aid)["status"] == "FAILED_DELIVERY"


def test_calendar_and_prior_day_never_replay_historical_slots(tmp_path):
    ledger = LocalJobLedger(tmp_path)
    claim(ledger)
    ledger.recover_interrupted(now(), lock_held=True)
    assert ledger.plan_due(now(14, 0, day=19), verified_trading=False, identity=IDENTITY) is None
    assert ledger.plan_due(now(14, 0, day=19), verified_trading=True, identity=IDENTITY) is None
    assert ledger.get_slot("2026-10-16 14:50")["status"] == "MISSED"


def test_job_state_and_export_immutable(tmp_path):
    ledger = LocalJobLedger(tmp_path)
    aid = claim(ledger)["attempt_id"]
    ledger.record_job(aid, "refresh_bars", status="running", now=now(), run_id="task-1")
    ledger.record_job(aid, "refresh_bars", status="succeeded", now=now(), run_id="task-1")
    with pytest.raises(ValueError):
        ledger.record_job(aid, "refresh_bars", status="running", now=now(), run_id="task-1")
    ledger.mark_export(aid, manifest=packet(now()), bundle_file="bundle_123.json", now=now())
    with pytest.raises(ValueError):
        ledger.mark_export(aid, manifest={**packet(now()), "sequence": 124}, bundle_file="bundle_124.json", now=now())


@pytest.mark.parametrize("bad", [datetime(2026, 10, 16, 14, 50), now().isoformat()])
def test_naive_and_non_datetime_clock_rejected(tmp_path, bad):
    with pytest.raises(ValueError):
        LocalJobLedger(tmp_path).plan_due(bad, verified_trading=True, identity=IDENTITY)
