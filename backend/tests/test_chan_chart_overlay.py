"""Chart overlays prefer a verified persisted Chan read and label the fallback."""
import json
from pathlib import Path

from app.main import app
from app.workspace.chan_chart_overlay import annotate_chart_chan, project_persisted_chan
from fastapi.testclient import TestClient


def _evidence():
    return {
        "available": True,
        "reason_code": None,
        "source": "persisted_r4c_observed_revision",
        "price_basis_id": "basis-research",
        "engine_id": "czsc",
        "engine_version": "1.0.1",
        "dialect_id": "r4c-observed-revision-v1",
        "observation_id": "obs-1",
        "settlement_status": "settled",
        "view_semantics": "latest_persisted_observed_revision_not_historical_pit",
        "counts": {"fx": 2, "bi": 2, "zs": 1},
        "structures": [
            {
                "kind": "bi",
                "direction": "Direction.Up",
                "source_start": "2026-09-01 15:00:00",
                "source_end": "2026-09-03 15:00:00",
                "geometry": {"high": 3.0, "low": 1.0},
            },
            {
                "kind": "bi",
                "direction": "向下",
                "source_start": "2026-09-03 15:00:00",
                "source_end": "2026-09-05 15:00:00",
                "geometry": {"high": 3.0, "low": 1.5},
            },
            {
                "kind": "bi",
                "direction": None,
                "source_start": "2026-09-05 15:00:00",
                "source_end": "2026-09-08 15:00:00",
                "geometry": {"high": 2.0, "low": 1.2},
            },
            {
                "kind": "zs",
                "source_start": "2026-09-01 15:00:00",
                "source_end": "2026-09-08 15:00:00",
                "geometry": {"zg": 2.8, "zd": 1.6},
            },
            {"kind": "fx", "source_start": "2026-09-01 15:00:00", "source_end": "2026-09-01 15:00:00", "geometry": {"high": 3.0, "low": 2.4}},
        ],
        "actionable": False,
    }


def test_persisted_chan_projects_bi_and_zhongshu_without_segments():
    view = project_persisted_chan(_evidence(), "basis-research")

    assert view["available"] is True
    assert view["drawable"] is True
    assert view["fallback_allowed"] is False
    assert view["qualified"] is False
    assert view["actionable"] is False
    assert view["segments"] == []
    assert view["bi"][0]["start_price"] == 1.0
    assert view["bi"][0]["end_price"] == 3.0
    assert view["bi"][0]["source"] == "persisted"
    assert view["bi"][1]["start_price"] == 3.0
    assert view["bi"][1]["end_price"] == 1.5
    assert view["undrawable_bi"] == 1
    assert view["zhongshu"] == [{
        "start_date": "2026-09-01 15:00:00",
        "end_date": "2026-09-08 15:00:00",
        "zd": 1.6,
        "zg": 2.8,
        "source": "persisted",
    }]
    assert "CZSC" in view["disclaimer"]


def test_price_basis_mismatch_keeps_persisted_off_the_chart_and_allows_simplified_fallback():
    view = project_persisted_chan(_evidence(), "other-basis")

    assert view["available"] is True
    assert view["drawable"] is False
    assert view["fallback_allowed"] is True
    assert view["reason_code"] == "price_basis_mismatch"
    assert view["bi"] == []
    assert "简化结构" in view["disclaimer"]
    assert view["actionable"] is False


def test_corrupt_persisted_chan_does_not_allow_simplified_fallback():
    view = project_persisted_chan({"available": False, "reason_code": "persistent_evidence_corrupt"}, "basis-research")

    assert view["drawable"] is False
    assert view["fallback_allowed"] is False
    assert "不改用简化结构" in view["disclaimer"]


def test_missing_snapshot_allows_labeled_simplified_fallback():
    chart = annotate_chart_chan({"research_price_basis_id": "basis-research", "actionable": False}, {"available": False, "reason_code": "snapshot_missing"})

    assert chart["chan_observation"]["fallback_allowed"] is True
    assert chart["chan_observation"]["reason_code"] == "snapshot_missing"
    assert "chan-structure-simplified-v1" in chart["chan_observation"]["disclaimer"]
    assert chart["actionable"] is False


def test_chart_route_attaches_non_actionable_chan_observation(bootstrapped):
    with TestClient(app) as client:
        response = client.get("/api/workspace/instruments/510300.SH/chart", params={"interval": "1d", "limit": 40})
    assert response.status_code == 200
    payload = response.json()
    observation = payload["chan_observation"]
    assert payload["actionable"] is False
    assert observation["actionable"] is False
    assert observation["qualified"] is False
    assert observation["fallback_allowed"] is True
    assert observation["reason_code"] == "snapshot_missing"
    assert payload["studies"]["chan_structure"]["algorithm"] == "chan-structure-simplified-v1"
    assert payload["studies"]["chan_structure"]["actionable"] is False


def test_frontend_fixture_matches_persisted_backend_projection():
    fixture = json.loads((Path(__file__).parent / "fixtures" / "chan_chart_projection.json").read_text(encoding="utf-8"))
    chart = fixture["chart"]

    assert chart["chan_observation"] == project_persisted_chan(
        fixture["evidence"], chart["research_price_basis_id"]
    )
    assert chart["chan_observation"]["zhongshu"][0]["start_date"] == "2026-09-01 15:00:00"
    assert chart["actionable"] is False
    assert chart["qualified"] is False
