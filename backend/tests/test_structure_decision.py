"""Structure (Wyckoff/Dow/ATR) participation in the live five-grade decision.

Owner instruction 2026-11-07: the three structure factors must join the
decision; their proportion is set later, so the weight is a provisional
config value (strategy.json signal_grade.structure_decision.weight).
The adjustment is bounded: at most one grade notch, it can neither create
可加仓 nor 减仓, and hard-rule grades (减仓 / 数据异常) are never overridden.
"""
import json
from pathlib import Path

from app.research.structure_decision import apply_structure_decision
from app.research.structure_shadow import compute_structure_shadow

CFG = {"enabled": True, "weight": 0.5, "max_shift": 1}


def _shadow(wy, dow, bucket="low"):
    block = {
        "wyckoff_score": wy, "wyckoff_confidence": 1.0,
        "dow_score": dow, "dow_confidence": 1.0,
        "atr_risk_bucket": bucket,
    }
    return compute_structure_shadow(block)


STRONG_UP = _shadow(1.0, 1.0)      # score 1.0
STRONG_DOWN = _shadow(-1.0, -1.0)  # score -1.0
WEAK_UP = _shadow(0.2, 0.2)        # score 0.2


def test_watch_upgrades_to_probe_on_strong_structure():
    d = apply_structure_decision("观望", STRONG_UP, CFG)
    assert d["applied"] is True and d["final_grade"] == "可试探"
    assert d["base_grade"] == "观望" and d["weight"] == 0.5


def test_probe_upgrades_to_entry_on_strong_structure():
    d = apply_structure_decision("可试探", STRONG_UP, CFG)
    assert d["applied"] is True and d["final_grade"] == "可入场"


def test_structure_cannot_create_top_grade():
    d = apply_structure_decision("可入场", STRONG_UP, CFG)
    assert d["applied"] is False and d["final_grade"] == "可入场"


def test_probe_downgrades_to_watch_on_strong_negative_structure():
    d = apply_structure_decision("可试探", STRONG_DOWN, CFG)
    assert d["applied"] is True and d["final_grade"] == "观望"


def test_structure_cannot_create_reduce():
    d = apply_structure_decision("观望", STRONG_DOWN, CFG)
    assert d["applied"] is False and d["final_grade"] == "观望"


def test_hard_reduce_never_overridden():
    d = apply_structure_decision("减仓", STRONG_UP, CFG)
    assert d["applied"] is False and d["final_grade"] == "减仓"


def test_data_abnormal_never_adjusted():
    d = apply_structure_decision("数据异常", STRONG_UP, CFG)
    assert d["applied"] is False and d["final_grade"] == "数据异常"


def test_weak_structure_does_not_move_grade():
    d = apply_structure_decision("观望", WEAK_UP, CFG)
    assert d["applied"] is False and d["final_grade"] == "观望"


def test_missing_shadow_no_change():
    d = apply_structure_decision("观望", None, CFG)
    assert d["applied"] is False and d["final_grade"] == "观望"


def test_extreme_atr_bucket_zeroes_structure_effect():
    d = apply_structure_decision("观望", _shadow(1.0, 1.0, bucket="extreme"), CFG)
    assert d["applied"] is False and d["final_grade"] == "观望"


def test_weight_zero_disables_effect():
    d = apply_structure_decision("观望", STRONG_UP, {"enabled": True, "weight": 0.0, "max_shift": 1})
    assert d["applied"] is False and d["final_grade"] == "观望"


def test_disabled_config_no_change():
    d = apply_structure_decision("观望", STRONG_UP, {"enabled": False, "weight": 0.5, "max_shift": 1})
    assert d["applied"] is False and d["final_grade"] == "观望"


def test_strategy_config_declares_structure_decision():
    strategy = json.loads((Path(__file__).resolve().parents[2] / "config" / "strategy.json").read_text(encoding="utf-8"))
    cfg = strategy["signal_grade"]["structure_decision"]
    assert cfg["enabled"] is True
    assert 0 < cfg["weight"] <= 1
    assert cfg["max_shift"] == 1
    assert strategy["signal_grade_version"].startswith("signal-grade-v0.3.5")
