from __future__ import annotations

from typing import Any, Iterable

HISTORICAL_CLASSIFICATION_CONTRACT_VERSION = "historical-classification-v1-current-metadata-only"


def current_metadata_classification_contract(instruments: Iterable[Any]) -> dict[str, Any]:
    rows = list(instruments or ())
    return {
        "version": HISTORICAL_CLASSIFICATION_CONTRACT_VERSION,
        "source": "Instrument.theme_l1/theme_l2/current_metadata",
        "effective_dated_history_available": False,
        "theme_point_in_time_qualified": False,
        "benchmark_membership_point_in_time_qualified": False,
        "current_classification_only": True,
        "historical_projection_policy": "diagnostic_only_current_labels_projected_over_history",
        "historical_backtest_theme_constraint_applied": False,
        "instrument_count": len(rows),
        "qualification": "UNKNOWN",
        "limitations": [
            "current theme labels have no persisted effective dates",
            "historical theme membership cannot be reconstructed from current Instrument metadata",
            "current labels may be used for present-day display and diagnostic grouping only",
            "historical transaction selection must not use current theme labels as a point-in-time constraint",
        ],
    }
