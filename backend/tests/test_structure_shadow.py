"""structure_shadow_v1 (Phase B1): frozen soft_c weights applied in parallel.

The shadow signal is a bypass research column. It must never feed back into
assign_grade / live five-档: these tests pin the frozen B0 formula
(soft_c_strict, verdict WEAK_PASS_KEEP_FROZEN) and the board wiring that keeps
``changes_live_grade`` False.
"""

from __future__ import annotations

import pytest

from app.research.structure_shadow import (
    SHADOW_WEIGHTS_ID,
    compute_structure_shadow,
)
from app.services.decision_board_service import _structure_shadow_for_row


def _structure(
    *,
    wy_score: float = 1.0,
    wy_conf: float = 1.0,
    dow_score: float = 1.0,
    dow_conf: float = 1.0,
    bucket: str = "low",
) -> dict:
    return {
        "schema_version": "structure_v1",
        "ts_code": "510300.SH",
        "as_of": "2026-11-05",
        "wyckoff_phase": "markup",
        "wyckoff_score": wy_score,
        "wyckoff_confidence": wy_conf,
        "dow_phase": "uptrend",
        "dow_score": dow_score,
        "dow_confidence": dow_conf,
        "atr14": 0.05,
        "atr_pct": 0.005,
        "atr_risk_bucket": bucket,
        "evidence": [],
        "research_only": True,
    }


def test_strong_structure_scores_full_long():
    out = compute_structure_shadow(_structure(), live_grade="可加仓")
    assert out is not None
    assert out["version"] == "structure_shadow_v1"
    assert out["weights_id"] == SHADOW_WEIGHTS_ID
    # (0.4*1*1 + 0.6*1*1) / 1.0 = 1.0, ATR low scale 1.0
    assert out["score"] == pytest.approx(1.0)
    assert out["position"] == 1.0
    assert out["signal"] == "偏多"
    assert out["agrees_with_live"] is True
    assert out["changes_live_grade"] is False
    assert out["research_only"] is True


def test_confidence_floor_zeroes_weak_evidence():
    out = compute_structure_shadow(_structure(wy_conf=0.3, dow_conf=0.3))
    assert out is not None
    assert out["score"] == 0.0
    assert out["position"] == 0.0
    assert out["signal"] == "中性"


def test_atr_extreme_blocks_signal_and_high_scales_down():
    extreme = compute_structure_shadow(_structure(bucket="extreme"))
    assert extreme is not None and extreme["score"] == 0.0 and extreme["position"] == 0.0

    high = compute_structure_shadow(_structure(bucket="high"))
    assert high is not None and high["score"] == pytest.approx(0.4)
    assert high["position"] == 1.0  # 0.4 still >= buy_thresh 0.30


def test_negative_structure_and_live_disagreement():
    out = compute_structure_shadow(
        _structure(wy_score=-1.0, dow_score=-1.0), live_grade="可入场"
    )
    assert out is not None
    assert out["score"] == pytest.approx(-1.0)
    assert out["position"] == -1.0
    assert out["signal"] == "偏空"
    assert out["agrees_with_live"] is False


def test_flat_band_and_half_positions():
    flat = compute_structure_shadow(_structure(wy_score=0.05, dow_score=0.05))
    assert flat is not None and flat["position"] == 0.0 and flat["signal"] == "中性"

    half = compute_structure_shadow(_structure(wy_score=0.2, dow_score=0.2))
    assert half is not None and half["position"] == 0.5 and half["signal"] == "弱偏多"

    half_neg = compute_structure_shadow(_structure(wy_score=-0.2, dow_score=-0.2))
    assert half_neg is not None and half_neg["position"] == -0.5
    assert half_neg["signal"] == "弱偏空"


def test_neutral_live_grade_agreement_rules():
    neutral_shadow = compute_structure_shadow(_structure(wy_score=0.0, dow_score=0.0), live_grade="观望")
    assert neutral_shadow is not None and neutral_shadow["agrees_with_live"] is True

    long_shadow = compute_structure_shadow(_structure(), live_grade="观望")
    assert long_shadow is not None and long_shadow["agrees_with_live"] is False

    unknown_live = compute_structure_shadow(_structure(), live_grade="数据异常")
    assert unknown_live is not None and unknown_live["agrees_with_live"] is None

    no_live = compute_structure_shadow(_structure())
    assert no_live is not None and no_live["agrees_with_live"] is None


def test_missing_or_invalid_structure_returns_none():
    assert compute_structure_shadow(None) is None
    assert compute_structure_shadow({}) is None
    assert compute_structure_shadow({"wyckoff_score": "bad"}) is None
    incomplete = _structure()
    del incomplete["dow_score"]
    assert compute_structure_shadow(incomplete) is None


def test_board_helper_pairs_structure_and_grade():
    out = _structure_shadow_for_row(structure_block=_structure(), grade="减仓")
    assert out is not None and out["signal"] == "偏多"
    assert out["agrees_with_live"] is False
    assert _structure_shadow_for_row(structure_block=None, grade="观望") is None
