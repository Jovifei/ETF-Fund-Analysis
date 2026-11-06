"""14:30 shadow decisions must be write-once and bind their inputs/versions."""
from __future__ import annotations

from datetime import date, datetime, timedelta
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.services.shadow_1430_snapshot import (
    verify_shadow_snapshot, write_1430_shadow_snapshot,
)


TZ = ZoneInfo("Asia/Shanghai")


def _write(tmp_path: Path, *, observations=None, code_sha="a" * 40):
    cutoff = datetime(2026, 11, 6, 14, 30, tzinfo=TZ)
    return write_1430_shadow_snapshot(
        reports_dir=tmp_path, target_date=date(2026, 11, 6),
        market_cutoff=cutoff, code_sha=code_sha,
        parameters_hash="b" * 64,
        observations=observations if observations is not None else {
            "510300.SH": {
                "actionable": False, "calibration_status": "not_calibrated",
                "state": "observe",
                "feature_available_at": (cutoff - timedelta(minutes=1)).isoformat(),
            },
        },
        source_evidence={"provider": "fixture_not_qualified"},
    )


def test_write_once_shadow_snapshot_protects_original_bytes(tmp_path):
    result = _write(tmp_path)
    path = Path(result["path"])
    first = path.read_bytes()
    assert verify_shadow_snapshot(path) is True
    assert result["qualification"] == "UNKNOWN"
    assert result["actionable"] is False
    assert result["calibration_status"] == "not_calibrated"
    envelope = json.loads(first)
    assert envelope["payload"]["market_cutoff"].endswith("+08:00")
    assert envelope["payload"]["git_commit_sha"] == "a" * 40
    with pytest.raises(FileExistsError):
        _write(tmp_path)
    assert path.read_bytes() == first


def test_shadow_rejects_post_cutoff_news_before_ever_creating_file(tmp_path):
    later = datetime(2026, 11, 6, 14, 31, tzinfo=TZ)
    with pytest.raises(ValueError, match="shadow_post_cutoff_input"):
        _write(tmp_path, observations={
            "510300.SH": {
                "actionable": False,
                "news_published_at": later.isoformat(),
            }
        })
    assert not list(tmp_path.glob("shadow_1430_*"))


def test_shadow_refuses_actionable_or_calibrated_fixtures(tmp_path):
    for claim in ({"actionable": True}, {"calibration_status": "calibrated"}):
        with pytest.raises(ValueError, match="shadow_snapshot_must_be_research_only"):
            _write(tmp_path, observations={"510300.SH": claim})


def test_shadow_refuses_promotion_claim_inside_observation(tmp_path):
    for claim in ({"qualification": "APPROVED"},
                  {"calibration_status": "some_other_claim"},
                  {"actionable": 1}):
        with pytest.raises(ValueError, match="shadow_snapshot_must_be_research_only"):
            _write(tmp_path, observations={"510300.SH": claim})
    assert not list(tmp_path.glob("shadow_1430_*"))
