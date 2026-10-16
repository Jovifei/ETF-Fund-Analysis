"""Bounded operational soak evidence; never infer authenticated UI acceptance.

Inputs are sanitized captures made by an independently authorized observer.
This module opens no network/database connection and does not alter scheduling.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.services.trading_calendar_service import TradingCalendarService
from app.workspace.local_atomic import write_json_atomic

SHANGHAI = ZoneInfo("Asia/Shanghai")
REPORT_VERSION = "local-stability-v1"
RESEARCH_TABLES = (
    "daily_bars", "quote_snapshots", "indicator_snapshots", "forecast_snapshots",
    "sector_snapshots", "support_resistance_snapshots", "market_context_snapshots",
    "market_bars", "decision_board_snapshots", "signal_snapshots",
    "chan_research_observations", "chan_structure_revisions",
    "chan_observed_transitions", "chan_research_stream_heads",
)
METRICS = ("exact_count", "n_tup_ins", "n_tup_upd", "n_tup_del", "heap_bytes", "total_bytes")
SLOTS = ("13:55", "14:20", "14:30", "14:45", "14:50", "14:55", "15:00", "15:15", "16:10")
DEFAULT_DEADLINES = {slot: 600 if slot in {"13:55", "15:15", "16:10"} else 120 for slot in SLOTS}


def _time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("missing timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("invalid_timestamp") from None
    if result.tzinfo is None:
        raise ValueError("timestamp requires timezone")
    return result


def _cloud(value: dict) -> dict[str, dict]:
    if value.get("transaction_read_only") != "on" or value.get("transaction_isolation") != "repeatable read":
        raise ValueError("read_only_repeatable_read_required")
    _time(value.get("captured_at"))
    _time(value.get("server_start"))
    # PostgreSQL uses SQL NULL until an explicit statistics reset. Missing
    # evidence is different from this known, stable "never reset" identity.
    if "stats_reset" not in value:
        raise ValueError("stats_reset_identity_missing")
    if value["stats_reset"] is not None:
        _time(value["stats_reset"])
    oid = value.get("database_oid")
    if isinstance(oid, bool) or not str(oid).isdigit() or int(oid) <= 0:
        raise ValueError("database_identity_missing")
    heads = value.get("schema_heads")
    if not isinstance(heads, list) or not heads or any(not isinstance(v, str) or not v for v in heads):
        raise ValueError("schema_identity_missing")
    tables = value.get("tables")
    if not isinstance(tables, list) or len(tables) != len(RESEARCH_TABLES):
        raise ValueError("exact_14_tables_required")
    names = [row.get("table_name") for row in tables if isinstance(row, dict)]
    if len(names) != len(tables) or set(names) != set(RESEARCH_TABLES):
        raise ValueError("missing_or_duplicate_table")
    for row in tables:
        if any(type(row.get(key)) is not int or row[key] < 0 for key in METRICS):
            raise ValueError("metric_missing_or_invalid")
    return {row["table_name"]: row for row in tables}


def compare_cloud_captures(before: dict, after: dict) -> dict:
    """Reset/missing counters are UNKNOWN, never a fabricated zero-growth PASS."""
    try:
        left, right = _cloud(before), _cloud(after)
        if _time(after["captured_at"]) <= _time(before["captured_at"]):
            raise ValueError("non_monotonic_capture_time")
        for key in ("database_oid", "server_start", "stats_reset", "schema_heads"):
            if str(before[key]) != str(after[key]):
                raise ValueError("database_or_stats_identity_changed")
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        return {"state": "UNKNOWN", "reason": str(error)}
    deltas = {table: {metric: right[table][metric] - left[table][metric] for metric in METRICS}
              for table in RESEARCH_TABLES}
    if any(deltas[table][metric] < 0 for table in RESEARCH_TABLES for metric in METRICS[1:4]):
        return {"state": "UNKNOWN", "reason": "write_counter_decreased", "deltas": deltas}
    changed = any(delta != 0 for row in deltas.values() for delta in row.values())
    return {"state": "FAIL" if changed else "PASS", "deltas": deltas,
            "scope": "exact_14_research_tables_only", "before_at": before["captured_at"],
            "after_at": after["captured_at"]}


def _runtime(before: dict, after: dict, source_sha: str, image_id: str) -> dict:
    try:
        if _time(after["captured_at"]) <= _time(before["captured_at"]):
            raise ValueError("non_monotonic_runtime_capture")
        pairs = []
        for capture in (before, after):
            services = capture.get("services")
            if not isinstance(services, list) or len(services) != 3:
                raise ValueError("three_runtime_roles_required")
            by_role = {item["role"]: item for item in services}
            if set(by_role) != {"api", "worker", "scheduler"}:
                raise ValueError("missing_runtime_role")
            if capture.get("source_sha") != source_sha:
                return {"state": "FAIL", "reason": "runtime_source_mismatch"}
            for role, service in by_role.items():
                expected_health = "disabled" if role == "scheduler" else "healthy"
                required = ("image_id", "state", "health", "restart_count", "oom_killed",
                            "started_at", "scheduler_enabled", "workspace_research_source")
                if any(key not in service for key in required):
                    raise ValueError("runtime_metric_missing")
                _time(service["started_at"])
                if (service["image_id"] != image_id or service["state"] != "running"
                        or service["health"] != expected_health or type(service["restart_count"]) is not int
                        or service["restart_count"] != 0 or service["oom_killed"] is not False
                        or service["scheduler_enabled"] is not False
                        or service["workspace_research_source"] != "local_bundle"):
                    return {"state": "FAIL", "reason": "unhealthy_or_changed_runtime"}
            pairs.append(by_role)
        if any(pairs[0][role]["started_at"] != pairs[1][role]["started_at"] for role in pairs[0]):
            raise ValueError("runtime_restart_boundary")
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        return {"state": "UNKNOWN", "reason": str(error)}
    return {"state": "PASS", "scope": "two_endpoint_runtime_observations_not_continuous_uptime"}


def _delivery(session: date, ledger: dict, source_sha: str, config_hash: str,
              scope_hash: str | None, deadlines: dict[str, int]) -> dict:
    slots = ledger.get("slots", [])
    attempts = ledger.get("attempts", [])
    jobs = ledger.get("jobs", [])
    observations = []
    for slot in SLOTS:
        slot_id = f"{session.isoformat()} {slot}"
        matches = [item for item in slots if item.get("slot_id") == slot_id]
        candidates = [item for item in attempts if item.get("slot_id") == slot_id]
        result = {"slot_id": slot_id, "state": "MISSING", "attempts": len(candidates)}
        if len(matches) != 1:
            observations.append(result)
            continue
        result["ledger_state"] = matches[0].get("status")
        delivered = [item for item in candidates if item.get("status") == "DELIVERED"]
        if matches[0].get("status") != "DELIVERED" or not delivered:
            result["state"] = "MISSED_OR_PENDING"
            observations.append(result)
            continue
        # First valid delivery determines slot latency; retries cannot rewrite history.
        candidate = min(delivered, key=lambda item: item.get("finished_at") or "")
        receipt = candidate.get("receipt") or {}
        attempt_jobs = [job for job in jobs if job.get("attempt_id") == candidate.get("attempt_id")]
        required = [job for job in attempt_jobs if job.get("required") is True
                    and not (job.get("job_name") == "upload" or str(job.get("job_name", "")).startswith("upload_"))]
        try:
            accepted_at = _time(receipt.get("received_at"))
            finished_at = _time(candidate.get("finished_at"))
            planned_at = datetime.combine(session, time.fromisoformat(slot), SHANGHAI)
            latency = (max(accepted_at, finished_at) - planned_at).total_seconds()
            receipt_ok = (receipt.get("status") in {"accepted", "already_accepted"}
                          and isinstance(candidate.get("bundle_id"), str) and len(candidate["bundle_id"]) == 64
                          and receipt.get("bundle_id") == candidate["bundle_id"]
                          and receipt.get("manifest_hash") == candidate["bundle_id"]
                          and type(candidate.get("sequence")) is int and candidate["sequence"] > 0
                          and type(receipt.get("sequence")) is int and receipt["sequence"] == candidate["sequence"])
            identities_ok = (candidate.get("code_sha") == source_sha and candidate.get("config_hash") == config_hash
                             and isinstance(candidate.get("scope_hash"), str) and len(candidate["scope_hash"]) == 64
                             and (scope_hash is None or candidate["scope_hash"] == scope_hash))
            def closed_research(job):
                # The dispatch callback records this only after validating its
                # database-bound typed proof. Raw quality remains false here.
                return (job.get("job_name") == "refresh_quotes"
                        and str(job.get("status")).lower() == "partial"
                        and job.get("details", {}).get("coverage_complete") is False
                        and job.get("details", {}).get("accepted_closed_session") is True)
            closed_jobs = [job for job in required if closed_research(job)]
            raw_coverage = bool(required) and all(job.get("details", {}).get("coverage_complete") is True for job in required)
            coverage_ok = bool(required) and all(
                (job.get("details", {}).get("coverage_complete") is True
                 and str(job.get("status")).lower() == "succeeded") or closed_research(job)
                for job in required)
            result.update(latency_seconds=latency, deadline_seconds=deadlines[slot],
                          receipt_matched=receipt_ok, identity_matched=identities_ok,
                          coverage_complete=raw_coverage, research_coverage_accepted=coverage_ok,
                          closed_research_jobs=len(closed_jobs),
                          input_qualification="closed_non_realtime_research" if closed_jobs else "source_quality_not_promoted",
                          bundle_id=candidate.get("bundle_id"),
                          failed_jobs=sum(str(job.get("status")).lower() in {"failed", "interrupted"} for job in attempt_jobs))
            result["state"] = "PASS" if (receipt_ok and identities_ok and coverage_ok
                and accepted_at >= planned_at and 0 <= latency <= deadlines[slot]) else "FAIL"
            if not required or any(type(job.get("details", {}).get("coverage_complete")) is not bool for job in required):
                result["state"] = "UNKNOWN"
        except (ValueError, TypeError, KeyError, AttributeError):
            result["state"] = "UNKNOWN"
        observations.append(result)
    state = "FAIL" if any(row["state"] == "FAIL" for row in observations) else (
        "UNKNOWN" if any(row["state"] == "UNKNOWN" for row in observations) else
        "PASS" if all(row["state"] == "PASS" for row in observations) else "PARTIAL")
    return {"state": state, "slots": observations, "scope": "validated_delivery_not_authenticated_consumer"}


def assess_session(*, session: date, ledger_summary: dict, cloud_before: dict, cloud_after: dict,
                   runtime_before: dict, runtime_after: dict, expected_source_sha: str,
                   expected_config_hash: str, expected_image_id: str, expected_scope_hash: str | None = None,
                   calendar=None, deadlines: dict[str, int] | None = None,
                   as_of: datetime | None = None) -> dict:
    if (re.fullmatch(r"[0-9a-f]{40}", expected_source_sha) is None
            or re.fullmatch(r"[0-9a-f]{64}", expected_config_hash) is None
            or re.fullmatch(r"sha256:[0-9a-f]{64}", expected_image_id) is None
            or (expected_scope_hash is not None and re.fullmatch(r"[0-9a-f]{64}", expected_scope_hash) is None)):
        raise ValueError("exact source/config/image/scope identities required")
    if deadlines is not None and (set(deadlines) != set(SLOTS)
            or any(type(value) is not int or value <= 0 for value in deadlines.values())):
        raise ValueError("positive deadline for every slot required")
    from app.core.config import Settings
    calendar = calendar or TradingCalendarService(Settings(_env_file=None))
    decision = calendar.decision(session)
    as_of = as_of or datetime.now(timezone.utc)
    if as_of.tzinfo is None:
        raise ValueError("observation cutoff requires timezone")
    report = {"report_version": REPORT_VERSION, "session": session.isoformat(),
              "generated_at": as_of.isoformat(), "state": "UNKNOWN",
              "calendar": {"verified": decision.verified, "is_trade_day": decision.is_trade_day,
                           "source": decision.source},
              "identity": {"source_sha": expected_source_sha, "config_hash": expected_config_hash,
                           "image_id": expected_image_id, "scope_hash": expected_scope_hash},
              "consumer_identity": {"state": "NOT_RUN", "reason": "accepted receipt is not authenticated page consumption"},
              "actionable": False, "calibration_status": "not_calibrated"}
    if not decision.verified or not decision.is_trade_day:
        report["reason"] = "verified_trading_day_required"
        return report
    checks = {"cloud_zero_growth": compare_cloud_captures(cloud_before, cloud_after),
              "runtime": _runtime(runtime_before, runtime_after, expected_source_sha, expected_image_id),
              "delivery": _delivery(session, ledger_summary, expected_source_sha, expected_config_hash,
                                    expected_scope_hash, deadlines or DEFAULT_DEADLINES)}
    start = datetime.combine(session, time(13, 55), SHANGHAI)
    end = datetime.combine(session, time(16, 30), SHANGHAI)
    try:
        window_ok = all(_time(value["captured_at"]).astimezone(SHANGHAI).date() == session
                        for value in (cloud_before, cloud_after, runtime_before, runtime_after))
        window_ok = window_ok and all(_time(value["captured_at"]) <= start for value in (cloud_before, runtime_before))
        window_ok = window_ok and all(_time(value["captured_at"]) >= end for value in (cloud_after, runtime_after))
        window_ok = window_ok and all(_time(value["captured_at"]) <= as_of
                                     for value in (cloud_before, cloud_after, runtime_before, runtime_after))
    except (ValueError, TypeError, KeyError):
        window_ok = False
    checks["observation_window"] = {"state": "PASS" if window_ok else "PARTIAL",
                                    "required_start": start.isoformat(), "required_end": end.isoformat()}
    report["checks"] = checks
    states = [item["state"] for item in checks.values()]
    report["state"] = "FAIL" if "FAIL" in states else ("UNKNOWN" if "UNKNOWN" in states else (
        "PASS" if all(state == "PASS" for state in states) else "PARTIAL"))
    return report


def record_stability(root: Path, report: dict) -> Path:
    """Store only the sanitized result, never raw provider or credential captures."""
    session = date.fromisoformat(report["session"])
    if report.get("report_version") != REPORT_VERSION:
        raise ValueError("unsupported stability report")
    path = root / "receipts" / "stability" / f"{session.isoformat()}.json"
    if path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))
        if previous.get("state") == "FAIL":
            raise ValueError("existing failed session retained; review evidence before a new acceptance run")
        if previous.get("state") == "PASS" and report.get("state") != "FAIL":
            return path
    write_json_atomic(path, report)
    return path


def summarize_stability(reports: list[dict] | Path) -> dict:
    if isinstance(reports, Path):
        reports = [json.loads(path.read_text(encoding="utf-8"))
                   for path in sorted((reports / "receipts" / "stability").glob("*.json"))]
    # Duplicate copies of one day do not create a second trading session.
    by_day = {item["session"]: item for item in reports if item.get("report_version") == REPORT_VERSION}
    eligible = [item for item in by_day.values() if item.get("state") == "PASS"
                and item.get("calendar", {}).get("verified") is True
                and item.get("calendar", {}).get("is_trade_day") is True]
    identities = {json.dumps(item["identity"], sort_keys=True) for item in eligible}
    passed = len(eligible) >= 2 and len(identities) == 1
    return {"report_version": REPORT_VERSION, "state": "FAIL" if any(item.get("state") == "FAIL" for item in by_day.values())
            else "PASS" if passed else "PARTIAL",
            "verified_trade_days": sorted(item["session"] for item in eligible),
            "required_trade_days": 2, "sessions": {day: item.get("state") for day, item in sorted(by_day.items())},
            "scope": "scheduled_delivery_and_14_research_tables_zero_growth",
            "consumer_identity": {"state": "NOT_RUN"}, "actionable": False,
            "calibration_status": "not_calibrated"}
