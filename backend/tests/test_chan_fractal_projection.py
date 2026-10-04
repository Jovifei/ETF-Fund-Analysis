"""Draw only explicit, verified persisted fractals without promoting their status."""
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal

import pytest
from app.db.base import Base
from app.models import ChanStructureRevision, Instrument
from app.research.chan_contract import (
    build_observation_id,
    build_structure_evidence,
    make_observation,
    prepare_research_input,
)
from app.services.chan_observation_service import ChanObservationPublisher
from app.services.chan_read_service import read_latest
from app.workspace.chan_chart_overlay import project_persisted_chan
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

BASIS = "fractal-test-basis"
STAMP = "2026-09-01 15:00:00"


def _fractal(**changes):
    return {
        "kind": "fx", "mark": "顶分型", "source_start": STAMP, "source_end": STAMP,
        "geometry": {"high": 3.0, "low": 1.0}, **changes,
    }


def _evidence(*structures, **changes):
    return {
        "available": True, "price_basis_id": BASIS,
        "counts": {"fx": len(structures), "bi": 0, "zs": 0},
        "settlement_status": "temporary",
        "view_semantics": "latest_persisted_observed_revision_not_historical_pit",
        "structures": list(structures), **changes,
    }


@pytest.mark.parametrize(("token", "mark", "price"), [
    ("顶分型", "top", 3.0), ("Mark.G", "top", 3.0),
    ("底分型", "bottom", 1.0), ("Mark.D", "bottom", 1.0),
])
def test_explicit_fractal_mark_selects_the_saved_extreme(token, mark, price):
    evidence = _evidence(_fractal(mark=token))
    before = deepcopy(evidence)
    projected = project_persisted_chan(evidence, BASIS)

    assert projected["fx"] == [{"date": STAMP, "price": price, "mark": mark, "source": "persisted"}]
    assert projected["undrawable_fx"] == 0
    assert projected["counts"]["fx"] == 1
    assert projected["qualified"] is projected["actionable"] is False
    assert projected["settlement_status"] == "temporary"
    assert projected["view_semantics"] == "latest_persisted_observed_revision_not_historical_pit"
    assert "confirmed_at" not in projected
    assert "engine_confirmation" not in projected
    assert evidence == before


@pytest.mark.parametrize("mark", [None, "", "unknown", "top", "bottom", "G", "D",
                                  "mark.g", "mark.d", " Mark.G ", "顶", "底", True, 1, {}, []])
def test_unknown_marks_cannot_be_inferred_from_direction_or_geometry(mark):
    projected = project_persisted_chan(_evidence(_fractal(mark=mark, direction="Direction.Up")), BASIS)
    assert projected["fx"] == []
    assert projected["undrawable_fx"] == 1


@pytest.mark.parametrize("field", ["high", "low"])
@pytest.mark.parametrize("value", [None, True, False, "3.0", "", "nan", float("nan"),
                                   float("inf"), float("-inf"), {}, [], Decimal("2.0"), 10**1000])
def test_both_extremes_must_be_strict_finite_numbers(field, value):
    geometry = {"high": 3.0, "low": 1.0, field: value}
    projected = project_persisted_chan(_evidence(_fractal(geometry=geometry)), BASIS)
    assert projected["fx"] == []
    assert projected["undrawable_fx"] == 1


@pytest.mark.parametrize("geometry", [{}, {"high": 3.0}, {"low": 1.0}, None, [],
                                      {"high": 1.0, "low": 3.0}])
def test_missing_or_inverted_geometry_is_not_drawn(geometry):
    projected = project_persisted_chan(_evidence(_fractal(geometry=geometry)), BASIS)
    assert projected["fx"] == []
    assert projected["undrawable_fx"] == 1


@pytest.mark.parametrize("geometry", [{"high": 3.0, "low": 0}, {"high": 3.0, "low": -1.0},
                                      {"high": 0, "low": 0}, {"high": -1.0, "low": -3.0}])
def test_nonpositive_extremes_are_not_etf_fractal_prices(geometry):
    projected = project_persisted_chan(_evidence(_fractal(geometry=geometry)), BASIS)
    assert projected["fx"] == []
    assert projected["undrawable_fx"] == 1


@pytest.mark.parametrize(("start", "end"), [
    (None, STAMP), (STAMP, None), (3, 3), (True, True), ([], []), ("", ""), ("  ", "  "),
    (STAMP, "2026-09-02 15:00:00"), (STAMP, "2026-09-01T15:00:00"),
])
def test_fractal_requires_the_same_nonempty_string_endpoint(start, end):
    projected = project_persisted_chan(_evidence(_fractal(source_start=start, source_end=end)), BASIS)
    assert projected["fx"] == []
    assert projected["undrawable_fx"] == 1


@pytest.mark.parametrize("mark", ["顶分型", "底分型"])
def test_equal_extremes_are_valid_without_inventing_direction(mark):
    projected = project_persisted_chan(_evidence(_fractal(mark=mark, geometry={"high": 2, "low": 2})), BASIS)
    assert projected["fx"][0]["price"] == 2.0
    assert projected["undrawable_fx"] == 0


def test_source_timestamp_and_rows_are_preserved_for_frontend_candle_resolution():
    stamp = "2026-09-01T23:00:00-07:00"
    top = _fractal(source_start=stamp, source_end=stamp)
    higher_top = {**top, "geometry": {"high": 4.0, "low": 1.0}}
    bottom = {**top, "mark": "底分型"}
    projected = project_persisted_chan(_evidence(top, deepcopy(top), higher_top, bottom), BASIS)
    assert projected["fx"] == [
        {"date": stamp, "price": price, "mark": mark, "source": "persisted"}
        for mark, price in [("top", 3.0), ("top", 3.0), ("top", 4.0), ("bottom", 1.0)]
    ]
    assert projected["undrawable_fx"] == 0


def test_undrawable_count_is_per_explicit_fractal_and_does_not_rewrite_saved_counts():
    projected = project_persisted_chan(_evidence(
        _fractal(), _fractal(mark=None), _fractal(geometry={}), None, {},
        {"kind": "unknown"}, counts={"fx": 12, "bi": 0, "zs": 0},
    ), BASIS)
    assert len(projected["fx"]) == 1
    assert projected["undrawable_fx"] == 2
    assert projected["counts"]["fx"] == 12


@pytest.mark.parametrize("reason", ["snapshot_missing", "persistent_evidence_corrupt", "unsupported_interval"])
def test_unavailable_evidence_cannot_leak_fractals(reason):
    projected = project_persisted_chan(_evidence(_fractal(), available=False, reason_code=reason), BASIS)
    assert projected["fx"] == []
    assert projected["undrawable_fx"] == 0
    assert projected["drawable"] is False
    assert projected["fallback_allowed"] is (reason != "persistent_evidence_corrupt")


@pytest.mark.parametrize("basis", ["different-basis", None, ""])
def test_unknown_or_mismatched_price_basis_cannot_leak_fractals(basis):
    projected = project_persisted_chan(_evidence(_fractal()), basis)
    assert projected["fx"] == []
    assert projected["undrawable_fx"] == 0
    assert projected["drawable"] is False
    assert projected["fallback_allowed"] is True


@pytest.mark.parametrize("evidence", [None, {}, {"available": True, "price_basis_id": BASIS},
                                      _evidence(structures=None)])
def test_missing_evidence_or_structure_list_has_no_invented_fractals(evidence):
    projected = project_persisted_chan(evidence, BASIS)
    assert projected["fx"] == []
    assert projected["undrawable_fx"] == 0


def test_fractal_projection_preserves_existing_bi_and_zs_behavior_and_metadata():
    evidence = _evidence(
        {"kind": "bi", "direction": "Direction.Up", "source_start": STAMP, "source_end": STAMP,
         "geometry": {"high": "3", "low": "1"}},
        {"kind": "zs", "source_start": STAMP, "source_end": STAMP,
         "geometry": {"zg": "2.8", "zd": "1.6"}},
        counts={"fx": 7, "bi": 1, "zs": 1}, transitions=[],
    )
    baseline = project_persisted_chan(evidence, BASIS)
    evidence["structures"].append(_fractal())
    projected = project_persisted_chan(evidence, BASIS)
    assert {key: value for key, value in projected.items() if key != "fx"} == {
        key: value for key, value in baseline.items() if key != "fx"
    }
    assert projected["bi"][0]["start_price"] == 1.0
    assert projected["bi"][0]["end_price"] == 3.0
    assert projected["zhongshu"][0]["zd"] == 1.6
    assert projected["zhongshu"][0]["zg"] == 2.8
    assert projected["segments"] == []


@pytest.fixture
def persisted_fractals(tmp_path):
    """Exercise the real immutable publisher and verifying read, on isolated SQLite."""
    engine = create_engine(f"sqlite:///{tmp_path / 'fractal-projection.sqlite3'}")
    Base.metadata.create_all(engine)
    code = "510300.SH"
    bars = [{
        "source_bar_id": f"fractal-bar-{index}", "timestamp": date(2026, 9, 1) + timedelta(days=index),
        "open": 2.0, "high": 3.0, "low": 1.0, "close": 2.0, "volume": 100.0, "amount": 200.0,
    } for index in range(12)]
    prepared = prepare_research_input(
        instrument=code, interval="D", series_id="fractal-projection-series",
        price_basis_id=BASIS, adjustment_version="none-v1", input_revision_id="fractal-projection-input",
        settlement_status="temporary", config_id="fractal-projection-config", bars=bars,
    )
    structures = []
    for index, mark in [(3, "顶分型"), (6, "底分型")]:
        bar = prepared.bars[index]
        structures.append(build_structure_evidence(
            prepared, observation_id=build_observation_id(prepared), kind="fx", direction=None, mark=mark,
            source_start=str(bar.timestamp), source_end=str(bar.timestamp),
            source_start_bar_id=bar.source_bar_id, source_end_bar_id=bar.source_bar_id,
            geometry={"high": 3.0, "low": 1.0}, engine_state=None,
        ))
    observation = make_observation(prepared, structures)
    try:
        with Session(engine) as db:
            db.add(Instrument(ts_code=code, symbol="510300", name="Synthetic ETF", kind="ETF",
                              exchange="SH", enabled=True))
            db.commit()
            ChanObservationPublisher(db).publish(observation)
            db.commit()
        yield engine, code, observation
    finally:
        engine.dispose()


def test_real_persisted_read_projects_top_and_bottom_without_confirmation_or_qualification(persisted_fractals):
    engine, code, observation = persisted_fractals
    with Session(engine) as db:
        evidence = read_latest(db, code, "D")
        projected = project_persisted_chan(evidence, BASIS)
        assert not db.new and not db.dirty and not db.deleted
    assert evidence["available"] is True
    assert evidence["engine_confirmation"] == "unknown"
    assert evidence["provider_called"] is evidence["engine_called"] is evidence["models_called"] is False
    assert evidence["qualification_changed"] is False
    assert projected["observation_id"] == observation.observation_id
    assert sorted(projected["fx"], key=lambda item: item["date"]) == [
        {"date": "2026-09-04 00:00:00", "price": 3.0, "mark": "top", "source": "persisted"},
        {"date": "2026-09-07 00:00:00", "price": 1.0, "mark": "bottom", "source": "persisted"},
    ]
    assert projected["undrawable_fx"] == 0
    assert projected["settlement_status"] == "temporary"
    assert projected["qualified"] is projected["actionable"] is False
    assert projected["revision_evidence"]["transitions"] == evidence["transitions"]


def test_tampered_persisted_fractal_is_blocked_by_verified_read(persisted_fractals):
    engine, code, _ = persisted_fractals
    with Session(engine) as db:
        revision = db.scalar(select(ChanStructureRevision))
        revision.payload_hash = "tampered-fractal-evidence"
        db.commit()
        evidence = read_latest(db, code, "D")
        projected = project_persisted_chan(evidence, BASIS)
    assert evidence["reason_code"] == "persistent_evidence_corrupt"
    assert projected["fx"] == []
    assert projected["drawable"] is projected["fallback_allowed"] is False
    assert projected["qualified"] is projected["actionable"] is False