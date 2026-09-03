from __future__ import annotations

from app.utils.current_decision import (
    DECISION_BOARD_SOURCE,
    MIXED_SOURCE,
    SIGNAL_GRADE_SOURCE,
    SIGNAL_SNAPSHOT_SOURCE,
    resolve_current_decision,
    summarize_sources,
)


def test_current_decision_precedence_prefers_board_then_grade_then_legacy_signal():
    decision = resolve_current_decision(
        decision_board_grade="观望",
        signal_grade_fallback="可入场",
        production_signal_state="加仓",
    )
    assert decision is not None
    assert decision.state == "观望"
    assert decision.source == DECISION_BOARD_SOURCE
    assert decision.canonical is True

    fallback = resolve_current_decision(
        signal_grade_fallback="可试探",
        production_signal_state="风险观察",
    )
    assert fallback is not None
    assert fallback.state == "可试探"
    assert fallback.source == SIGNAL_GRADE_SOURCE
    assert fallback.canonical is True

    legacy = resolve_current_decision(production_signal_state="持有")
    assert legacy is not None
    assert legacy.state == "持有"
    assert legacy.source == SIGNAL_SNAPSHOT_SOURCE
    assert legacy.canonical is False


def test_current_decision_empty_values_do_not_create_fake_state():
    assert resolve_current_decision(
        decision_board_grade=" ",
        signal_grade_fallback=None,
        production_signal_state="",
    ) is None


def test_source_summary_is_explicit_for_mixed_per_instrument_resolution():
    assert summarize_sources([DECISION_BOARD_SOURCE, DECISION_BOARD_SOURCE]) == DECISION_BOARD_SOURCE
    assert summarize_sources([SIGNAL_GRADE_SOURCE]) == SIGNAL_GRADE_SOURCE
    assert summarize_sources([DECISION_BOARD_SOURCE, SIGNAL_GRADE_SOURCE]) == MIXED_SOURCE
