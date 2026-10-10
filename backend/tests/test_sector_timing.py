"""Unit tests for research-only sector timing observation."""
from __future__ import annotations

from app.utils.sector_timing import (
    OBSERVATION_ADD,
    OBSERVATION_NEUTRAL,
    OBSERVATION_REDUCE,
    aggregate_market_evidence_by_theme,
    build_sector_timing_observation,
    empty_sector_timing_observation,
    infer_afternoon_slot_hint,
    map_sector_name_to_theme_l1,
)


SAMPLE_TAXONOMY = {
    "exact": {
        "半导体": {"theme_l1": "科技", "theme_l2": "半导体", "style_tags": ["成长"], "exposure_keys": []},
    },
    "keyword_rules": [
        {"keywords": ["银行"], "theme_l1": "金融", "theme_l2": "银行", "style_tags": ["红利"], "exposure_keys": []},
        {"keywords": ["煤炭"], "theme_l1": "资源能源", "theme_l2": "煤炭", "style_tags": ["周期"], "exposure_keys": []},
    ],
}


def test_empty_rows_yield_stable_non_actionable_payload() -> None:
    payload = build_sector_timing_observation([])
    assert payload["actionable"] is False
    assert payload["research_only"] is True
    assert payload["calibration_status"] == "not_calibrated"
    assert payload["summary"]["theme_count"] == 0
    assert payload["themes"] == []
    assert payload["intended_slots"] == ["14:30", "14:45"]
    assert payload["digest"]["actionable"] is False
    assert payload["digest"]["field_path"] == "sector_timing.digest"
    assert payload["field_paths"]["digest"] == "sector_timing.digest"


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
    assert payload["digest"]["add_themes"] == ["红利"]
    assert "偏强观察" in payload["digest"]["headline"]
    theme = payload["themes"][0]
    assert theme["theme_l1"] == "红利"
    assert theme["observation"] == OBSERVATION_ADD
    assert theme["add_grade_count"] == 2
    assert theme["reduce_grade_count"] == 0
    assert theme["actionable"] is False
    assert theme["market_corroboration"]["available"] is False
    assert theme["market_corroboration"]["alignment"] == "unavailable"
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


def test_map_sector_name_exact_and_keyword() -> None:
    exact = map_sector_name_to_theme_l1("半导体", SAMPLE_TAXONOMY)
    assert exact is not None
    assert exact["theme_l1"] == "科技"
    assert exact["match_kind"] == "exact"
    keyword = map_sector_name_to_theme_l1("国有大型银行", SAMPLE_TAXONOMY)
    assert keyword is not None
    assert keyword["theme_l1"] == "金融"
    assert keyword["match_kind"] == "keyword"
    assert map_sector_name_to_theme_l1("完全无关板块XYZ", SAMPLE_TAXONOMY) is None
    assert map_sector_name_to_theme_l1("半导体", None) is None


def test_market_corroboration_supports_add_without_overriding_grades() -> None:
    rows = [
        {"ts_code": "588000.SH", "theme_l1": "科技", "grade": "可加仓", "return_5d": 0.02},
        {"ts_code": "512480.SH", "theme_l1": "科技", "grade": "可入场", "return_5d": 0.01},
    ]
    evidence = [
        {
            "sector_name": "半导体",
            "board_type": "industry",
            "pct_change": 1.5,
            "up_count": 40,
            "down_count": 10,
            "trade_date": "2026-10-10",
            "source": "akshare",
        }
    ]
    payload = build_sector_timing_observation(
        rows, slot_hint="14:45", market_evidence=evidence, taxonomy=SAMPLE_TAXONOMY
    )
    theme = payload["themes"][0]
    assert theme["observation"] == OBSERVATION_ADD
    corr = theme["market_corroboration"]
    assert corr["available"] is True
    assert corr["alignment"] == "supports_add"
    assert corr["mean_pct_change"] == 1.5
    assert corr["actionable"] is False
    assert payload["summary"]["market_corroboration_theme_count"] == 1
    assert payload["digest"]["market_corroboration_theme_count"] == 1
    assert "市+1.50%" in payload["digest"]["headline"]
    # Grades on input rows unchanged
    assert rows[0]["grade"] == "可加仓"


def test_unmapped_market_evidence_is_not_invented() -> None:
    rows = [{"ts_code": "510300.SH", "theme_l1": "宽基", "grade": "观望", "return_5d": 0.0}]
    evidence = [
        {
            "sector_name": "完全无关板块XYZ",
            "board_type": "industry",
            "pct_change": 9.9,
            "up_count": 99,
            "down_count": 1,
            "trade_date": "2026-10-10",
            "source": "akshare",
        }
    ]
    payload = build_sector_timing_observation(
        rows, market_evidence=evidence, taxonomy=SAMPLE_TAXONOMY
    )
    corr = payload["themes"][0]["market_corroboration"]
    assert corr["available"] is False
    assert corr["alignment"] == "unavailable"
    assert corr["mean_pct_change"] is None
    assert aggregate_market_evidence_by_theme(evidence, SAMPLE_TAXONOMY) == {}


def test_infer_afternoon_slot_hint() -> None:
    assert infer_afternoon_slot_hint(14, 30) == "14:30"
    assert infer_afternoon_slot_hint(14, 45) == "14:45"
    assert infer_afternoon_slot_hint(10, 30) is None
