"""One terminal result contract, separate from investment/data qualification."""
from __future__ import annotations

TERMINAL = {"succeeded", "partial", "failed", "skipped", "cancelled"}

def count(value):
    if isinstance(value, (list, dict, tuple, set)):
        return len(value)
    return max(0, int(value)) if isinstance(value, (int, float)) else 0

def coverage_outcome(requested, completed, **metadata):
    requested, completed = int(requested), int(completed)
    if requested <= 0:
        status = "partial"
    elif completed <= 0:
        status = "failed"
    else:
        status = "succeeded" if completed >= requested else "partial"
    return {**metadata, "requested": requested, "completed": completed,
            "coverage_complete": bool(requested and completed >= requested), "status": status}

def normalize_outcome(result):
    """No success-by-default. Counters can downgrade an optimistic producer."""
    if not isinstance(result, dict) or not result:
        return {"status": "failed", "reason": "missing_result_contract"}
    result = dict(result)
    explicit = result.get("status")
    if explicit in {"failed", "cancelled", "skipped"}:
        return result
    errors = max(count(result.get(k)) for k in ("failures", "failed_steps", "missing", "skipped"))
    successes = sum(count(result.get(k)) for k in ("created", "updated", "inserted", "unchanged"))
    successes = max(successes, count(result.get("completed")), count(result.get("observed")), count(result.get("instruments")))
    if "requested" in result and "completed" in result:
        derived = coverage_outcome(result["requested"], result["completed"])["status"]
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
    return result
