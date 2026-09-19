"""Terminal execution outcome, independent of data/trading qualification.

Input inventory sizes never prove successful output. Producers with no record
counters (e.g. report generation) must explicitly state their terminal status.
"""
from __future__ import annotations
import math

TERMINAL = {"succeeded", "partial", "failed", "skipped", "cancelled"}
OUTPUT_KEYS = ("created", "updated", "inserted", "unchanged", "completed", "observed")
ERROR_KEYS = ("failures", "failed_steps", "missing", "skipped", "errors", "error", "missing_codes", "degraded", "price_only")


def count(value):
    if value is None:
        return 0
    if isinstance(value, (list, dict, tuple, set)):
        return len(value)
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0 or int(value) != value):
        raise ValueError("invalid_result_counter")
    return int(value)


def coverage_outcome(requested, completed, **metadata):
    try:
        if not isinstance(requested, (int, float)) or not isinstance(completed, (int, float)):
            raise ValueError("invalid_result_counter")
        requested, completed = count(requested), count(completed)
        if completed > requested:
            raise ValueError("completion_exceeds_requested")
    except (ValueError, TypeError, OverflowError):
        return {**metadata, "requested": 0, "completed": 0,
                "coverage_complete": False, "status": "failed", "reason": "invalid_coverage_counters"}
    stale_count = count(metadata.get("stale_count", 0))
    status = "partial" if stale_count else "partial" if not requested else "failed" if not completed else "succeeded" if completed == requested else "partial"
    return {**metadata, "requested": requested, "completed": completed,
            "coverage_complete": bool(requested and completed == requested and not stale_count), "status": status}


def normalize_outcome(result):
    """No success-by-default; evidence can downgrade optimistic producers."""
    if not isinstance(result, dict) or not result:
        return {"status": "failed", "coverage_complete": False, "reason": "missing_result_contract"}
    result = dict(result)
    explicit = result.get("status")
    if explicit in {"failed", "cancelled", "skipped"}:
        result["coverage_complete"] = False
        return result
    try:
        errors = max(count(result.get(k)) for k in ERROR_KEYS)
        successes = max(sum(count(result.get(k)) for k in OUTPUT_KEYS[:4]),
                        count(result.get("completed")), count(result.get("observed")))
        steps = result.get("steps")
        if isinstance(steps, dict):
            step_states = [normalize_outcome(value)["status"] for value in steps.values()]
            successes = max(successes, sum(state == "succeeded" for state in step_states))
            errors = max(errors, sum(state != "succeeded" for state in step_states))
    except (ValueError, TypeError, OverflowError):
        return {**result, "status": "failed", "coverage_complete": False, "reason": "invalid_result_counter"}
    if "requested" in result and "completed" in result:
        coverage = coverage_outcome(
            result["requested"], result["completed"], stale_count=result.get("stale_count", 0)
        )
        derived = coverage["status"]
        if coverage.get("reason"):
            return {**result, **coverage}
    elif errors:
        derived = "partial" if successes else "failed"
    elif successes:
        derived = "succeeded"
    elif explicit in TERMINAL:
        derived = explicit
    else:
        derived = "failed"
        result.setdefault("reason", "missing_terminal_status")
    if (result.get("coverage_complete") is False or errors or explicit == "partial") and derived == "succeeded":
        derived = "partial"
    nested = result.get("input")
    if isinstance(nested, dict) and normalize_outcome(nested)["status"] != "succeeded" and derived == "succeeded":
        derived = "partial"
    result["status"] = derived
    if derived != "succeeded":
        result["coverage_complete"] = False
    return result
