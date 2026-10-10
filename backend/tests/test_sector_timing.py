"""Unit tests for research-only sector timing observation."""
from __future__ import annotations

from app.utils.sector_timing import (
    OBSERVATION_ADD,
    OBSERVATION_NEUTRAL,
    OBSERVATION_REDUCE,
    build_sector_timing_observation,
    empty_sector_timing_observation,
)


def test_empty_rows_yield_stable_non_actionable_payload() -> None:
    payload = build_sector_timing_observation([])
    assert payload["actionable"] is False
    assert payload["research_only"] is True
    assert payload["calibration_status"] == "not_calibrated"
    assert payload["summary"]["theme_count"] == 0
    assert payload["themes"] == []
    assert payload["intended_slots"] == ["14:30", "14:45"]


def test_empty_helper_matches_empty_build() -> None:
    assert empty_sector_timing_observation(slot_hint="14:30")["slot_hint"] == "14:30"
    assert empty_sector_timing_observation()["themes"] == []


def test_add_side_theme_observation() -> None:
    rows = [
        {"ts_code": "510880.SH", "theme_l1": "红利", "grade": "可加仓", "return_5d": 0.02},
        {"ts_code": "515180.SH", "theme_l1": "红利", "grade": "可入场", "return_5d": 0.01},
        {"ts_code": "512890.SH", "theme_l1": "红利", "grade": "观望", "return_5d": 0.005},
    ]
    payload = build_sector_timing_observation(rows, slot_hint="14:30")
    assert payload["actionable"] is False
    assert payload["slot_hint"] == "14:30"
    assert payload["summary"]["add_observation_themes"] == ["红利"]
    theme = payload["themes"][0]
    assert theme["theme_l1"] == "红利"
    assert theme["observation"] == OBSERVATION_ADD
    assert theme["add_grade_count"] == 2
    assert theme["reduce_grade_count"] == 0
    assert theme["actionable"] is False
    assert "510880.SH" in theme["sample_codes"]


def test_reduce_side_theme_observation() -> None:
    rows = [
        {"ts_code": "588000.SH", "theme_l1": "科技", "grade": "减仓", "return_5d": -0.04},
        {"ts_code": "159915.SZ", "theme_l1": "科技", "grade": "减仓", "return_5d": -0.03},
        {"ts_code": "512480.SH", "theme_l1": "科技", "grade": "观望", "return_5d": -0.02},
    ]
    payload = build_sector_timing_observation(rows)
    assert payload["summary"]["reduce_observation_themes"] == ["科技"]
    theme = payload["themes"][0]
    assert theme["observation"] == OBSERVATION_REDUCE
    assert theme["reduce_grade_count"] == 2


def test_missing_theme_rows_are_ignored_and_grades_untouched() -> None:
    rows = [
        {"ts_code": "511990.SH", "theme_l1": "", "grade": "可加仓", "return_5d": 0.0},
        {"ts_code": "511880.SH", "theme_l1": None, "grade": "减仓", "return_5d": -0.01},
        {"ts_code": "518880.SH", "theme_l1": "商品", "grade": "观望", "return_5d": 0.0},
    ]
    payload = build_sector_timing_observation(rows)
    assert payload["summary"]["theme_count"] == 1
    assert payload["themes"][0]["observation"] == OBSERVATION_NEUTRAL
    # Input grades must remain caller-owned; helper only reads them.
    assert rows[0]["grade"] == "可加仓"
    assert rows[1]["grade"] == "减仓"


def test_mixed_themes_rank_add_before_reduce() -> None:
    rows = [
        {"ts_code": "A", "theme_l1": "防御", "grade": "可加仓", "return_5d": 0.03},
        {"ts_code": "B", "theme_l1": "防御", "grade": "可试错", "return_5d": 0.02},
        {"ts_code": "C", "theme_l1": "成长", "grade": "减仓", "return_5d": -0.05},
        {"ts_code": "D", "theme_l1": "成长", "grade": "减仓", "return_5d": -0.04},
    ]
    payload = build_sector_timing_observation(rows)
    assert [item["theme_l1"] for item in payload["themes"]] == ["防御", "成长"]
    assert payload["themes"][0]["observation"] == OBSERVATION_ADD
    assert payload["themes"][1]["observation"] == OBSERVATION_REDUCE
    assert payload["themes"][0]["rank"] == 1
    assert all(item["actionable"] is False for item in payload["themes"])
