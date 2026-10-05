from __future__ import annotations

from collections.abc import Iterable
from typing import Any

HISTORICAL_CLASSIFICATION_CONTRACT_VERSION = "historical-classification-v2-content-bound"
_SOURCE = "Instrument.theme_l1/theme_l2/current_metadata"
_POLICY = "diagnostic_only_current_labels_projected_over_history"
_UNSPECIFIED = object()


def current_metadata_classification_contract(instruments: Iterable[Any]) -> dict[str, Any]:
    rows = list(instruments or ())
    classifications: dict[str, dict[str, Any]] = {}
    for item in rows:
        code = getattr(item, "ts_code", None)
        if not isinstance(code, str) or not code.strip() or code != code.strip():
            raise ValueError("classification instrument code must be a nonempty canonical string")
        if code in classifications:
            raise ValueError("duplicate classification instrument code")
        classifications[code] = {
            "theme_l1": getattr(item, "theme_l1", None),
            "theme_l2": getattr(item, "theme_l2", None),
        }
    contract = {
        "version": HISTORICAL_CLASSIFICATION_CONTRACT_VERSION,
        "source": _SOURCE,
        "effective_dated_history_available": False,
        "theme_point_in_time_qualified": False,
        "benchmark_membership_point_in_time_qualified": False,
        "current_classification_only": True,
        "historical_projection_policy": _POLICY,
        "historical_backtest_theme_constraint_applied": False,
        "instrument_count": len(rows),
        "instrument_classifications": dict(sorted(classifications.items())),
        "qualification": "UNKNOWN",
        "limitations": [
            "current theme labels have no persisted effective dates",
            "historical theme membership cannot be reconstructed from current Instrument metadata",
            "current labels may be used for present-day display and diagnostic grouping only",
            "historical transaction selection must not use current theme labels as a point-in-time constraint",
        ],
    }
    issues = classification_contract_issues(contract)
    if issues:
        raise ValueError(",".join(issues))
    return contract


def classification_contract_issues(
    contract: Any, *, expected_codes: Any = _UNSPECIFIED, allow_superset: bool = False,
) -> list[str]:
    """Validate this current-label evidence contract without granting PIT status."""
    if not isinstance(contract, dict) or not contract:
        return ["classification_contract_missing"]
    issues: list[str] = []
    if contract.get("version") != HISTORICAL_CLASSIFICATION_CONTRACT_VERSION:
        issues.append("classification_contract_version_mismatch")
    if contract.get("source") != _SOURCE:
        issues.append("classification_source_mismatch")
    if contract.get("historical_projection_policy") != _POLICY:
        issues.append("classification_projection_policy_mismatch")
    classifications = contract.get("instrument_classifications")
    if not isinstance(classifications, dict):
        issues.append("classification_snapshot_missing")
    else:
        count = contract.get("instrument_count")
        if type(count) is not int or count != len(classifications):
            issues.append("classification_snapshot_count_mismatch")
        for code, labels in classifications.items():
            if (
                not isinstance(code, str) or not code.strip() or code != code.strip()
                or not isinstance(labels, dict)
                or set(labels) != {"theme_l1", "theme_l2"}
                or any(value is not None and not isinstance(value, str) for value in labels.values())
            ):
                issues.append("classification_snapshot_invalid")
                break
    if expected_codes is not _UNSPECIFIED:
        try:
            expected = (list(expected_codes) if expected_codes is not None
                        and not isinstance(expected_codes, (str, bytes, dict)) else None)
        except TypeError:
            expected = None
        if (
            expected is None
            or any(not isinstance(code, str) or not code.strip() or code != code.strip() for code in expected)
            or len(set(expected)) != len(expected)
        ):
            issues.append("classification_expected_codes_invalid")
        elif isinstance(classifications, dict):
            actual_codes = set(classifications)
            expected_set = set(expected)
            matches = expected_set <= actual_codes if allow_superset else expected_set == actual_codes
            if not matches:
                issues.append("classification_instrument_coverage_mismatch")
    required_flags = {
        "effective_dated_history_available": False,
        "theme_point_in_time_qualified": False,
        "benchmark_membership_point_in_time_qualified": False,
        "historical_backtest_theme_constraint_applied": False,
        "current_classification_only": True,
    }
    if any(contract.get(key) is not value for key, value in required_flags.items()):
        issues.append("classification_qualification_contract_mismatch")
    if contract.get("qualification") != "UNKNOWN":
        issues.append("classification_qualification_contract_mismatch")
    return list(dict.fromkeys(issues))
