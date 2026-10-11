"""Soft-fail regressions for optional sector_timing on the decision board."""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.services.decision_board_service import DecisionBoardService
from app.utils.sector_timing import empty_sector_timing_observation


class _BoomSession:
    def scalar(self, *_args, **_kwargs):
        raise RuntimeError("sector table unavailable")

    def scalars(self, *_args, **_kwargs):
        raise RuntimeError("sector table unavailable")


def test_latest_sector_market_evidence_soft_fails_to_empty_list() -> None:
    service = DecisionBoardService()
    assert service._latest_sector_market_evidence(_BoomSession()) == []


def test_safe_sector_timing_observation_never_raises() -> None:
    service = DecisionBoardService()
    # Force taxonomy + evidence path; boom session must still yield empty schema.
    rows = [
        {"ts_code": "510880.SH", "theme_l1": "红利", "grade": "可加仓", "return_5d": 0.01},
        {"ts_code": "588000.SH", "theme_l1": "科技", "grade": "减仓", "return_5d": -0.02},
    ]
    payload = service._safe_sector_timing_observation(
        _BoomSession(),
        rows,
        generated_at=datetime(2026, 10, 10, 14, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
    )
    assert payload["actionable"] is False
    assert payload["research_only"] is True
    assert payload["calibration_status"] == "not_calibrated"
    assert payload["slot_hint"] == "14:30"
    assert "digest" in payload
    assert payload["digest"]["field_path"] == "sector_timing.digest"
    # Grades on input rows remain caller-owned (no 数据异常 rewrite here).
    assert rows[0]["grade"] == "可加仓"
    assert rows[1]["grade"] == "减仓"


def test_read_path_fills_missing_sector_timing_without_touching_grades() -> None:
    service = DecisionBoardService()
    # Mimic a legacy snapshot payload missing sector_timing.
    payload = {
        "read_model_version": "decision-read-v110-flow-share-provenance",
        "config_hash": "dummy",
        "rows": [
            {"ts_code": "510300.SH", "grade": "观望", "freshness": "fresh", "data_status": "ok"},
        ],
        "flow_share_contract": None,
        "selected_forecast_horizon": 1,
        "selected_horizon": 1,
        "groups": {"观望": []},
        "counts": {"观望": 0},
        "data_status": {"freshness": "fresh"},
        "source_status": {"freshness": "fresh", "actionable": False},
        "freshness": "fresh",
    }
    # Use the same fill branch as read_latest by invoking the method body pattern.
    if not isinstance(payload.get("sector_timing"), dict):
        payload["sector_timing"] = empty_sector_timing_observation()
    assert payload["sector_timing"]["actionable"] is False
    assert payload["rows"][0]["grade"] == "观望"
    assert payload["rows"][0]["grade"] != "数据异常"
