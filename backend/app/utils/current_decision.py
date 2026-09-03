from __future__ import annotations

from dataclasses import dataclass

DECISION_BOARD_SOURCE = "decision_board_snapshot"
SIGNAL_GRADE_SOURCE = "signal_grade_fallback"
SIGNAL_SNAPSHOT_SOURCE = "signal_snapshot_last_resort"
MIXED_SOURCE = "mixed_per_instrument"
NO_SOURCE = "unavailable"


@dataclass(frozen=True, slots=True)
class CurrentDecision:
    state: str
    source: str
    canonical: bool


def _clean(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def resolve_current_decision(
    *,
    decision_board_grade: object = None,
    signal_grade_fallback: object = None,
    production_signal_state: object = None,
) -> CurrentDecision | None:
    """Resolve one instrument's current state with explicit source lineage.

    Current user-facing conclusions prefer the persisted decision-board grade,
    then the deterministic SignalGradeService fallback. Production SignalSnapshot
    state is retained only as a last-resort compatibility/audit value.
    """

    board = _clean(decision_board_grade)
    if board is not None:
        return CurrentDecision(board, DECISION_BOARD_SOURCE, True)

    grade = _clean(signal_grade_fallback)
    if grade is not None:
        return CurrentDecision(grade, SIGNAL_GRADE_SOURCE, True)

    legacy = _clean(production_signal_state)
    if legacy is not None:
        return CurrentDecision(legacy, SIGNAL_SNAPSHOT_SOURCE, False)

    return None


def summarize_sources(sources: list[str]) -> str:
    clean = {source for source in sources if source}
    if not clean:
        return NO_SOURCE
    if len(clean) == 1:
        return next(iter(clean))
    return MIXED_SOURCE
