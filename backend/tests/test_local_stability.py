from copy import deepcopy
from datetime import date, datetime, timezone, timedelta
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from pathlib import Path
from functools import lru_cache
import pytest

from app.workspace.local_stability import (
    RESEARCH_TABLES, assess_session, compare_cloud_captures,
    record_stability, summarize_stability, FULL_STAGES, FAST_STAGES, FULL_SLOTS,
    EXECUTION_LINEAGE_VERSION,
)
from app.workspace.shadow_bundle import digest


SHA = "a" * 40
CONFIG = "b" * 64
IMAGE = "sha256:" + "c" * 64
SLOTS = ("13:55", "14:20", "14:30", "14:45", "14:50", "14:55", "15:00", "15:15", "16:10")
UNIVERSE = ["510300.SH"]
SCOPE = digest(UNIVERSE)


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


def populate_ledger(root, day="2026-10-16"):
    """Synthetic observer evidence through the real persistence/export APIs."""
    from app.workspace.local_job_ledger import LocalJobLedger
    from app.workspace.local_stability import SHANGHAI
    ledger = LocalJobLedger(root)
    identity = {"code_sha": SHA, "config_hash": CONFIG, "scope_hash": SCOPE}
    for sequence, slot in enumerate(SLOTS, 1):
        planned = datetime.fromisoformat(f"{day}T{slot}:00").replace(tzinfo=SHANGHAI)
        due = ledger.plan_due(planned, verified_trading=True, identity=identity, slots=SLOTS)
        attempt = ledger.claim(due["slot_id"], planned, identity=identity, lock_held=True)
        mode = "full" if slot in FULL_SLOTS else "fast"
        stage_names = FULL_STAGES if mode == "full" else FAST_STAGES
        for stage in sorted(stage_names):
            closed = slot == "16:10" and stage == "refresh_quotes"
            ledger.record_job(attempt["attempt_id"], stage, status="partial" if closed else "succeeded",
                now=planned + timedelta(seconds=20), required=True,
                run_id=f"run_{sequence}_{stage}",
                details={"coverage_complete": not closed, "accepted_closed_session": closed})
        lineage = {"contract_version": EXECUTION_LINEAGE_VERSION, "mode": mode,
                   "execution_hash": digest({"fixture_execution": day}),
                   "config_file_hash": digest({"fixture_config": day}),
                   "base_input_hash": digest({"fixture_base": slot}),
                   "quote_batch_hash": digest({"fixture_quotes": slot})}
        ledger.record_job(attempt["attempt_id"], "execution_contract", status="succeeded",
            now=planned + timedelta(seconds=30), required=False,
            details={"execution_mode": mode, **{key: value for key, value in lineage.items()
                                                if key not in {"contract_version", "mode"}}})
        manifest = {"contract_version": "local-display-v2", "sequence": sequence,
                    "code_sha": SHA, "config_hash": CONFIG, "universe": UNIVERSE,
                    "generated_at": (planned + timedelta(seconds=25)).isoformat(),
                    "expires_at": (planned + timedelta(hours=2)).isoformat(),
                    "execution_lineage": lineage}
        ledger.mark_export_intent(attempt["attempt_id"], manifest=manifest,
            bundle_file=f"bundle_{sequence}.json", now=planned + timedelta(seconds=30))
        ledger.mark_export(attempt["attempt_id"], manifest=manifest,
            bundle_file=f"bundle_{sequence}.json", now=planned + timedelta(seconds=35))
        ledger.record_job(attempt["attempt_id"], "upload_1", status="running",
                          now=planned + timedelta(seconds=40))
        receipt = {"bundle_id": digest(manifest), "manifest_hash": digest(manifest),
                   "sequence": sequence, "status": "accepted",
                   "received_at": (planned + timedelta(seconds=50)).isoformat()}
        ledger.mark_delivered(attempt["attempt_id"], manifest=manifest, receipt=receipt,
                              now=planned + timedelta(seconds=50))
    return ledger


@lru_cache(maxsize=3)
def _jobs_snapshot(day):
    with TemporaryDirectory(prefix="etf-stability-test-") as folder:
        return populate_ledger(Path(folder), day).summary(day)


def jobs(day="2026-10-16"):
    return deepcopy(_jobs_snapshot(day))


def session(day="2026-10-16", **overrides):
    args = dict(session=date.fromisoformat(day), ledger_summary=jobs(day),
                cloud_before=cloud(day), cloud_after=cloud(day, "16:35"),
                runtime_before=runtime(day), runtime_after=runtime(day, "16:35"),
                expected_source_sha=SHA, expected_config_hash=CONFIG,
                expected_scope_hash=SCOPE,
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
    attempt_id = next(row["attempt_id"] for row in ledger["attempts"] if row["slot_id"].endswith("14:30"))
    ledger["jobs"] = [row for row in ledger["jobs"] if not (
        row["attempt_id"] == attempt_id and row["job_name"].startswith("upload_"))]
    ledger["jobs"].extend([
        {"attempt_id": attempt_id, "job_name": "upload_1", "required": True,
         "status": "failed", "details": {}},
        {"attempt_id": attempt_id, "job_name": "upload_2", "required": True,
         "status": "succeeded", "details": {}},
    ])
    result = session(ledger_summary=ledger)
    assert result["state"] == "PASS"
    assert result["checks"]["delivery"]["slots"][2]["failed_jobs"] == 1
    del ledger["jobs"][0]["details"]["coverage_complete"]
    assert session(ledger_summary=ledger)["checks"]["delivery"]["state"] == "UNKNOWN"


def test_real_ledger_summary_contract_is_consumed(tmp_path):
    ledger = populate_ledger(tmp_path)
    report = session(ledger_summary=ledger.summary("2026-10-16"),
                     expected_scope_hash=SCOPE)
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
        quote = next(row for row in ledger["jobs"] if row["job_name"] == "refresh_quotes")
        quote.update(status="partial", details={"coverage_complete": False,
                                                "accepted_closed_session": True})
        quote.update(changes)
        assert session(ledger_summary=ledger)["state"] != "PASS"


def test_quote_only_is_not_a_complete_delivered_pipeline():
    ledger = jobs()
    ledger["jobs"] = [job for job in ledger["jobs"] if job["job_name"] == "refresh_quotes"]
    assert session(ledger_summary=ledger)["state"] != "PASS"


def test_missing_execution_context_cannot_pass():
    ledger = jobs()
    ledger["jobs"] = [job for job in ledger["jobs"] if job["job_name"] != "execution_contract"]
    assert session(ledger_summary=ledger)["state"] != "PASS"


def test_receipt_does_not_substitute_for_successful_upload_job():
    ledger = jobs()
    ledger["jobs"] = [job for job in ledger["jobs"] if not job["job_name"].startswith("upload")]
    assert session(ledger_summary=ledger)["state"] != "PASS"


@pytest.mark.parametrize("missing", ["refresh_signals", "refresh_decision_board", "refresh_bars", "refresh_forecasts"])
def test_missing_required_stage_blocks_full_delivery(missing):
    ledger = jobs()
    ledger["jobs"] = [job for job in ledger["jobs"] if job["job_name"] != missing]
    assert session(ledger_summary=ledger)["state"] != "PASS"


@pytest.mark.parametrize("change", ["absent", "duplicate_within_attempt", "reused_from_other_slot"])
def test_task_run_identity_is_required_unique_and_not_reused(change):
    ledger = jobs()
    stages = [job for job in ledger["jobs"] if job["job_name"] in FULL_STAGES]
    if change == "absent":
        stages[0].pop("run_id")
    elif change == "duplicate_within_attempt":
        stages[1]["run_id"] = stages[0]["run_id"]
    else:
        later = next(job for job in stages if job["attempt_id"] != stages[0]["attempt_id"])
        later["run_id"] = stages[0]["run_id"]
    assert session(ledger_summary=ledger)["state"] != "PASS"


def _rebind(attempt):
    """Adversarial in-memory rewrite also recomputes hashes; context must agree."""
    attempt["bundle_id"] = digest(attempt["manifest"])
    attempt["receipt"].update(bundle_id=attempt["bundle_id"], manifest_hash=attempt["bundle_id"],
                              sequence=attempt["manifest"]["sequence"])
    attempt["sequence"] = attempt["manifest"]["sequence"]


@pytest.mark.parametrize("change", ["missing_manifest", "manifest_tamper", "context_hash", "lineage_hash",
                                   "scope_tamper", "extra_lineage", "missing_context_hash", "backdated", "sequence_reuse"])
def test_manifest_context_scope_receipt_and_order_must_all_agree(change):
    ledger = jobs()
    attempt = ledger["attempts"][1]
    context = next(job for job in ledger["jobs"] if job["attempt_id"] == attempt["attempt_id"]
                   and job["job_name"] == "execution_contract")
    if change == "missing_manifest":
        attempt.pop("manifest")
    elif change == "manifest_tamper":
        attempt["manifest"]["sequence"] += 123
    elif change == "context_hash":
        context["details"]["execution_hash"] = "f" * 64
    elif change == "missing_context_hash":
        context["details"].pop("quote_batch_hash")
    else:
        if change == "lineage_hash":
            attempt["manifest"]["execution_lineage"]["execution_hash"] = "f" * 64
        elif change == "scope_tamper":
            attempt["manifest"]["universe"] = ["512480.SH"]
        elif change == "extra_lineage":
            attempt["manifest"]["execution_lineage"]["extra"] = "unsupported"
        elif change == "backdated":
            attempt["manifest"]["generated_at"] = "2026-10-16T13:55:10+08:00"
        elif change == "sequence_reuse":
            attempt["manifest"]["sequence"] = ledger["attempts"][0]["sequence"]
        _rebind(attempt)
    assert session(ledger_summary=ledger)["state"] != "PASS"


def test_actual_full_fallback_needs_full_stages_and_cannot_claim_fast():
    ledger = jobs()
    attempt = ledger["attempts"][1]  # 14:20 normally fast.
    context = next(job for job in ledger["jobs"] if job["attempt_id"] == attempt["attempt_id"]
                   and job["job_name"] == "execution_contract")
    for name in sorted(FULL_STAGES - FAST_STAGES):
        ledger["jobs"].append({"attempt_id": attempt["attempt_id"], "job_name": name,
            "run_id": f"fallback_{name}", "status": "succeeded", "required": True,
            "details": {"coverage_complete": True}})
    assert session(ledger_summary=ledger)["state"] == "FAIL"  # Six actual stages labeled fast.
    context["details"]["execution_mode"] = "full"
    attempt["manifest"]["execution_lineage"]["mode"] = "full"
    _rebind(attempt)
    assert session(ledger_summary=ledger)["state"] == "PASS"
    first = ledger["attempts"][0]  # 13:55 must never be marked fast.
    context = next(job for job in ledger["jobs"] if job["attempt_id"] == first["attempt_id"]
                   and job["job_name"] == "execution_contract")
    context["details"]["execution_mode"] = "fast"
    first["manifest"]["execution_lineage"]["mode"] = "fast"
    _rebind(first)
    assert session(ledger_summary=ledger)["state"] == "FAIL"


def test_unknown_scope_duplicate_stage_and_legacy_acceptance_cannot_pass():
    assert session(expected_scope_hash=None)["state"] == "UNKNOWN"
    ledger = jobs()
    ledger["jobs"].append(deepcopy(ledger["jobs"][0]))
    assert session(ledger_summary=ledger)["state"] == "FAIL"
    legacy = session()
    legacy["report_version"] = "local-stability-v1"
    assert summarize_stability([legacy, legacy])["state"] == "PARTIAL"
