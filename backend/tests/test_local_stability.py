from copy import deepcopy
from datetime import date, datetime, timezone, timedelta
from types import SimpleNamespace
import pytest

from app.workspace.local_stability import (
    RESEARCH_TABLES, assess_session, compare_cloud_captures,
    record_stability, summarize_stability,
)


SHA = "a" * 40
CONFIG = "b" * 64
IMAGE = "sha256:" + "c" * 64
SLOTS = ("13:55", "14:20", "14:30", "14:45", "14:50", "14:55", "15:00", "15:15", "16:10")


class Calendar:
    def decision(self, day):
        return SimpleNamespace(verified=True, is_trade_day=day.weekday() < 5,
                               source="verified-test-calendar")


def cloud(day="2026-10-16", when="13:45"):
    return {
        "captured_at": f"{day}T{when}:00+08:00",
        "transaction_read_only": "on", "transaction_isolation": "repeatable read",
        "database_oid": "123", "server_start": "2026-10-01T00:00:00Z",
        "stats_reset": "2026-10-01T00:00:00Z", "schema_heads": ["f0"],
        "tables": [{"table_name": table, "exact_count": 100, "n_tup_ins": 100,
                    "n_tup_upd": 0, "n_tup_del": 0, "heap_bytes": 8192,
                    "total_bytes": 16384} for table in RESEARCH_TABLES],
    }


def runtime(day="2026-10-16", when="13:45"):
    return {"captured_at": f"{day}T{when}:00+08:00", "source_sha": SHA,
            "services": [{"role": role, "image_id": IMAGE, "state": "running",
                          "health": "healthy" if role != "scheduler" else "disabled",
                          "restart_count": 0, "oom_killed": False,
                          "started_at": "2026-10-16T00:00:00Z",
                          "scheduler_enabled": False,
                          "workspace_research_source": "local_bundle"}
                         for role in ("api", "worker", "scheduler")]}


def jobs(day="2026-10-16"):
    return {
        "ledger_version": "local-job-ledger-v1",
        "slots": [{"slot_id": f"{day} {slot}", "session": day, "slot": slot,
                   "status": "DELIVERED", "planned_at": f"{day}T{slot}:00+08:00"} for slot in SLOTS],
        "attempts": [{"attempt_id": slot, "slot_id": f"{day} {slot}",
                      "status": "DELIVERED", "attempt_no": 1,
                      "finished_at": f"{day}T{slot}:50+08:00",
                      "bundle_id": "d" * 64, "sequence": 1,
                      "code_sha": SHA, "config_hash": CONFIG, "scope_hash": "e" * 64,
                      "receipt": {"status": "accepted", "bundle_id": "d" * 64,
                                  "manifest_hash": "d" * 64,
                                  "sequence": 1, "received_at": f"{day}T{slot}:50+08:00"}}
                     for slot in SLOTS],
        "jobs": [{"attempt_id": slot, "job_name": "refresh_quotes", "required": True,
                  "status": "SUCCEEDED", "details": {"coverage_complete": True}}
                 for slot in SLOTS],
    }


def session(day="2026-10-16", **overrides):
    args = dict(session=date.fromisoformat(day), ledger_summary=jobs(day),
                cloud_before=cloud(day), cloud_after=cloud(day, "16:35"),
                runtime_before=runtime(day), runtime_after=runtime(day, "16:35"),
                expected_source_sha=SHA, expected_config_hash=CONFIG,
                expected_image_id=IMAGE, calendar=Calendar(),
                as_of=datetime(2026, 10, 20, tzinfo=timezone.utc))
    args.update(overrides)
    return assess_session(**args)


def test_cloud_requires_every_metric_not_only_row_counts():
    before, after = cloud(), cloud(when="16:35")
    assert compare_cloud_captures(before, after)["state"] == "PASS"
    after["tables"][0]["n_tup_upd"] += 1
    assert compare_cloud_captures(before, after)["state"] == "FAIL"
    after = cloud(when="16:35")
    del after["tables"][0]["heap_bytes"]
    assert compare_cloud_captures(before, after)["state"] == "UNKNOWN"


def test_postgres_never_reset_null_identity_is_valid_but_missing_is_unknown():
    before, after = cloud(), cloud(when="16:35")
    before["stats_reset"] = after["stats_reset"] = None
    before["database_oid"] = after["database_oid"] = "16384"
    before["server_start"] = after["server_start"] = "2026-10-13T22:25:09.55433+08:00"
    assert compare_cloud_captures(before, after)["state"] == "PASS"
    del after["stats_reset"]
    assert compare_cloud_captures(before, after)["state"] == "UNKNOWN"


def test_cloud_reset_duplicate_missing_identity_or_time_is_unknown():
    for change in (lambda x: x.update(stats_reset="2026-10-16T15:00:00Z"),
                   lambda x: x.update(database_oid="999"),
                   lambda x: x.update(stats_reset=None),
                   lambda x: x["tables"].append(deepcopy(x["tables"][0])),
                   lambda x: x.update(captured_at="2026-10-16T13:00:00+08:00"),
                   lambda x: x.update(transaction_read_only="off")):
        after = cloud(when="16:35")
        change(after)
        assert compare_cloud_captures(cloud(), after)["state"] == "UNKNOWN"


def test_one_complete_verified_day_is_not_two_day_acceptance():
    report = session()
    assert report["state"] == "PASS"
    assert report["consumer_identity"]["state"] == "NOT_RUN"
    assert summarize_stability([report])["state"] == "PARTIAL"
    assert summarize_stability([report, report])["state"] == "PARTIAL"


def test_two_complete_distinct_trading_days_pass_only_operational_scope():
    report = summarize_stability([session(), session("2026-10-19")])
    assert report["state"] == "PASS"
    assert report["verified_trade_days"] == ["2026-10-16", "2026-10-19"]
    assert report["consumer_identity"]["state"] == "NOT_RUN"
    assert report["actionable"] is False


def test_short_window_or_unverified_day_cannot_pass():
    assert session(cloud_before=cloud(when="15:00"))["state"] == "PARTIAL"
    assert session(runtime_after=runtime(when="15:00"))["state"] == "PARTIAL"
    assert session("2026-10-17")["state"] == "UNKNOWN"
    class Unverified(Calendar):
        def decision(self, day):
            return SimpleNamespace(verified=False, is_trade_day=True, source="weekday")
    assert session(calendar=Unverified())["state"] == "UNKNOWN"


def test_missing_missed_late_unproven_or_mixed_identity_delivery_blocks_pass():
    cases = []
    missing = jobs(); missing["slots"].pop(); cases.append(missing)
    for changes in ({"status": "SUPERSEDED"}, {"status": "MISSED"},
                    {"finished_at": "2026-10-16T14:35:00+08:00"},
                    {"code_sha": "e" * 40}, {"config_hash": "f" * 64},
                    {"receipt": None}):
        candidate = jobs()
        candidate["attempts"][0].update(changes)
        cases.append(candidate)
    uncovered = jobs(); uncovered["jobs"][0]["details"]["coverage_complete"] = False
    cases.append(uncovered)
    for candidate in cases:
        assert session(ledger_summary=candidate)["state"] != "PASS"


def test_cloud_writes_restart_or_config_drift_fails_session():
    after = cloud(when="16:35")
    after["tables"][0]["n_tup_ins"] += 1
    assert session(cloud_after=after)["state"] == "FAIL"
    running = runtime(when="16:35")
    running["services"][0]["restart_count"] = 1
    assert session(runtime_after=running)["state"] == "FAIL"
    running = runtime(when="16:35")
    running["services"][0]["scheduler_enabled"] = True
    assert session(runtime_after=running)["state"] == "FAIL"


def test_persisted_report_is_bounded_to_sanitized_results(tmp_path):
    report = session()
    record_stability(tmp_path, report)
    summary = summarize_stability(tmp_path)
    assert summary["state"] == "PARTIAL"
    assert len(list((tmp_path / "receipts" / "stability").glob("*.json"))) == 1


def test_failed_day_cannot_be_overwritten_by_later_pass(tmp_path):
    report = session()
    report["state"] = "FAIL"
    record_stability(tmp_path, report)
    with pytest.raises(ValueError, match="failed session retained"):
        record_stability(tmp_path, session())
    assert summarize_stability(tmp_path)["state"] == "FAIL"


def test_source_change_across_days_does_not_form_two_day_pass():
    first, second = session(), session("2026-10-19")
    second["identity"]["source_sha"] = "f" * 40
    assert summarize_stability([first, second])["state"] == "PARTIAL"


def test_runtime_restart_boundary_is_unknown_and_non_auth_proof_stays_unrun():
    after = runtime(when="16:35")
    after["services"][0]["started_at"] = "2026-10-16T07:00:00Z"
    assert session(runtime_after=after)["checks"]["runtime"]["state"] == "UNKNOWN"


def test_future_captures_running_jobs_and_deletions_do_not_pass():
    assert session(as_of=datetime(2026, 10, 16, 6, tzinfo=timezone.utc))["state"] == "PARTIAL"
    running = jobs()
    running["jobs"][0]["status"] = "RUNNING"
    assert session(ledger_summary=running)["state"] == "FAIL"
    after = cloud(when="16:35")
    after["tables"][0]["exact_count"] -= 1
    assert compare_cloud_captures(cloud(), after)["state"] == "FAIL"


def test_upload_retry_is_retained_but_not_collector_coverage():
    ledger = jobs()
    ledger["jobs"].extend([
        {"attempt_id": "14:30", "job_name": "upload_1", "required": True,
         "status": "failed", "details": {}},
        {"attempt_id": "14:30", "job_name": "upload_2", "required": True,
         "status": "succeeded", "details": {}},
    ])
    result = session(ledger_summary=ledger)
    assert result["state"] == "PASS"
    assert result["checks"]["delivery"]["slots"][2]["failed_jobs"] == 1
    del ledger["jobs"][0]["details"]["coverage_complete"]
    assert session(ledger_summary=ledger)["checks"]["delivery"]["state"] == "UNKNOWN"


def test_real_ledger_summary_contract_is_consumed(tmp_path):
    from app.workspace.local_job_ledger import LocalJobLedger
    from app.workspace.shadow_bundle import digest
    from app.workspace.local_stability import SHANGHAI

    ledger = LocalJobLedger(tmp_path)
    identity = {"code_sha": SHA, "config_hash": CONFIG, "scope_hash": digest(["510300.SH"])}
    for sequence, slot in enumerate(SLOTS, 1):
        planned = datetime.fromisoformat(f"2026-10-16T{slot}:00").replace(tzinfo=SHANGHAI)
        due = ledger.plan_due(planned, verified_trading=True, identity=identity, slots=SLOTS)
        claimed = ledger.claim(due["slot_id"], planned, identity=identity, lock_held=True)
        closed = slot == "16:10"
        ledger.record_job(claimed["attempt_id"], "refresh_quotes", status="partial" if closed else "succeeded",
                          now=planned, required=True, details={"coverage_complete": not closed,
                                                              "accepted_closed_session": closed})
        manifest = {"contract_version": "local-display-v2", "sequence": sequence,
                    "code_sha": SHA, "config_hash": CONFIG, "universe": ["510300.SH"],
                    "expires_at": (planned + timedelta(hours=2)).isoformat()}
        ledger.mark_export(claimed["attempt_id"], manifest=manifest,
                           bundle_file=f"bundle_{sequence}.json", now=planned)
        receipt = {"bundle_id": digest(manifest), "manifest_hash": digest(manifest),
                   "sequence": sequence, "status": "accepted",
                   "received_at": (planned + timedelta(seconds=50)).isoformat()}
        ledger.mark_delivered(claimed["attempt_id"], manifest=manifest, receipt=receipt,
                              now=planned + timedelta(seconds=50))
    report = session(ledger_summary=ledger.summary("2026-10-16"),
                     expected_scope_hash=identity["scope_hash"])
    assert report["state"] == "PASS"
    closed = report["checks"]["delivery"]["slots"][-1]
    assert closed["coverage_complete"] is False
    assert closed["research_coverage_accepted"] is True
    assert closed["input_qualification"] == "closed_non_realtime_research"


def test_closed_research_exception_is_only_for_explicit_partial_quote_proof():
    for changes in ({"job_name": "refresh_bars"}, {"status": "succeeded"},
                    {"details": {"coverage_complete": False}},
                    {"details": {"accepted_closed_session": True}}):
        ledger = jobs()
        ledger["jobs"][0].update(status="partial", details={"coverage_complete": False,
                                                            "accepted_closed_session": True})
        ledger["jobs"][0].update(changes)
        assert session(ledger_summary=ledger)["state"] != "PASS"
