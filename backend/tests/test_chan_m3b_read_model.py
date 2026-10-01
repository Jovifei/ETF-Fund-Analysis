from __future__ import annotations

from datetime import date, datetime, timedelta
from importlib import import_module
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.db.base import Base
from app.utils.hashing import stable_hash
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import Session


@pytest.fixture
def read_runtime(tmp_path):
    import app.models.entities  # noqa: F401
    import app.workspace.models  # noqa: F401
    from app.models import Instrument

    engine = create_engine(f"sqlite:///{tmp_path / 'chan-read-model.sqlite3'}")
    Base.metadata.create_all(engine)
    code = "510300.SH"
    with Session(engine) as db:
        db.add(
            Instrument(
                ts_code=code,
                symbol="510300",
                name="Synthetic ETF",
                kind="ETF",
                exchange="SH",
                enabled=True,
            )
        )
        db.add(
            Instrument(
                ts_code="501018.SH",
                symbol="501018",
                name="Synthetic LOF",
                kind="LOF",
                exchange="SH",
                enabled=True,
            )
        )
        db.add(
            Instrument(
                ts_code="600000.SH",
                symbol="600000",
                name="Synthetic stock",
                kind="STOCK",
                exchange="SH",
                enabled=True,
            )
        )
        db.commit()
    try:
        yield SimpleNamespace(engine=engine, code=code)
    finally:
        engine.dispose()


def _make_observation(
    code: str = "510300.SH",
    *,
    interval: str = "D",
    count: int = 12,
    price_basis_id: str = "basis-raw-v1",
    revision: str | None = None,
    settlement_status: str = "settled",
    with_structure: bool = True,
    high: float | None = 103.0,
):
    contract = import_module("app.research.chan_contract")
    start = date(2026, 1, 1)
    bars = []
    for index in range(count):
        close = 100.0 + index * 0.1
        bars.append(
            {
                "source_bar_id": f"{code}-{interval}-bar-{index:04d}",
                "timestamp": start + timedelta(days=index),
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1000.0 + index,
                "amount": close * (1000.0 + index),
            }
        )
    config_id = f"config-{interval}-v1"
    prepared = contract.prepare_research_input(
        instrument=code,
        interval=interval,
        series_id=f"series-{code}-{interval}-{price_basis_id}",
        price_basis_id=price_basis_id,
        adjustment_version="none-v1",
        input_revision_id=revision or f"revision-{count}-{uuid4().hex}",
        settlement_status=settlement_status,
        config_id=config_id,
        bars=bars,
    )
    structures = []
    if with_structure and high is not None:
        bar = prepared.bars[5]
        structures.append(
            contract.build_structure_evidence(
                prepared,
                observation_id=contract.build_observation_id(prepared),
                kind="fx",
                direction=None,
                mark="顶分型",
                source_start=str(bar.timestamp),
                source_end=str(bar.timestamp),
                source_start_bar_id=bar.source_bar_id,
                source_end_bar_id=bar.source_bar_id,
                geometry={"high": high, "low": high - 2.0},
                engine_state="synthetic-state-v1",
            )
        )
    return contract.make_observation(prepared, structures)


def _publish(engine, observation):
    from app.services.chan_observation_service import ChanObservationPublisher

    with Session(engine) as db:
        result = ChanObservationPublisher(db).publish(observation)
        db.commit()
        return result


def test_read_latest_missing_head_is_bounded_snapshot_missing(read_runtime):
    from app.services.chan_read_service import read_latest

    with Session(read_runtime.engine) as db:
        result = read_latest(db, read_runtime.code, "D")

    assert result["available"] is False
    assert result["reason_code"] == "snapshot_missing"
    assert result["ts_code"] == read_runtime.code
    assert result["interval"] == "D"
    assert result["provider_called"] is False
    assert result["engine_called"] is False
    assert result["models_called"] is False
    assert result["qualification_changed"] is False
    assert result["actionable"] is False
    assert "structures" not in result
    assert "payload_json" not in result
    assert "bars" not in result


def test_read_latest_returns_verified_bounded_persisted_structures(read_runtime):
    from app.services.chan_read_service import read_latest

    observation = _make_observation()
    _publish(read_runtime.engine, observation)

    with Session(read_runtime.engine) as db:
        result = read_latest(db, read_runtime.code, "D")

    assert result["available"] is True
    assert result["reason_code"] is None
    assert result["view_semantics"] == "latest_persisted_observed_revision_not_historical_pit"
    assert result["stream_id"]
    assert result["observation_id"] == observation.observation_id
    assert result["sequence_number"] == 1
    assert result["settlement_status"] == "settled"
    assert result["cutoff"] == 12
    assert result["input_hash"] == observation.input_hash
    assert result["engine_confirmation"] == "unknown"
    assert result["application_observation_status"] == "observed"
    assert result["counts"] == {"fx": 1, "bi": 0, "zs": 0}
    assert result["structures"][0]["structure_key"] == observation.structures[0].structure_key
    assert result["structures"][0]["revision_id"] == observation.structures[0].revision_id
    assert result["transitions"][0]["status"] == "OBSERVED_NEW"
    assert result["provider_called"] is False
    assert result["engine_called"] is False
    assert result["models_called"] is False
    assert result["qualification_changed"] is False
    assert result["actionable"] is False
    assert "payload_json" not in result
    assert "bars" not in result


def test_read_latest_selects_newest_cutoff_across_basis_streams(read_runtime):
    from app.services.chan_read_service import read_latest

    _publish(read_runtime.engine, _make_observation(count=12, price_basis_id="basis-raw-v1"))
    later = _make_observation(count=13, price_basis_id="basis-qfq-v1")
    _publish(read_runtime.engine, later)

    with Session(read_runtime.engine) as db:
        result = read_latest(db, read_runtime.code, "D")

    assert result["available"] is True
    assert result["observation_id"] == later.observation_id
    assert result["price_basis_id"] == "basis-qfq-v1"
    assert result["cutoff"] == 13


def test_read_latest_fails_closed_on_equal_maximal_stream_cutoffs(read_runtime):
    from app.services.chan_read_service import read_latest

    _publish(read_runtime.engine, _make_observation(count=12, price_basis_id="basis-raw-v1"))
    _publish(read_runtime.engine, _make_observation(count=12, price_basis_id="basis-qfq-v1"))

    with Session(read_runtime.engine) as db:
        result = read_latest(db, read_runtime.code, "D")

    assert result["available"] is False
    assert result["reason_code"] == "ambiguous_stream_head"
    assert "structures" not in result


def test_read_latest_preserves_period_settlement_and_valid_empty_observations(read_runtime):
    from app.services.chan_read_service import read_latest

    temporary = _make_observation(interval="W", count=12, settlement_status="temporary")
    settled = _make_observation(
        interval="W",
        count=13,
        settlement_status="settled",
        revision="weekly-settled-r2",
    )
    _publish(read_runtime.engine, temporary)
    _publish(read_runtime.engine, settled)
    month = _make_observation(
        interval="M",
        count=2,
        with_structure=False,
        settlement_status="temporary",
        revision="monthly-empty-r1",
    )
    _publish(read_runtime.engine, month)

    with Session(read_runtime.engine) as db:
        weekly = read_latest(db, read_runtime.code, "W")
        monthly = read_latest(db, read_runtime.code, "M")

    assert weekly["available"] is True
    assert weekly["settlement_status"] == "settled"
    assert weekly["sequence_number"] == 2
    assert monthly["available"] is True
    assert monthly["settlement_status"] == "temporary"
    assert monthly["counts"] == {"fx": 0, "bi": 0, "zs": 0}
    assert monthly["structures"] == []


@pytest.mark.parametrize(
    "damage",
    ["observation_hash", "observation_column", "structure_payload", "missing_revision", "head_sequence"],
)
def test_read_latest_fails_closed_on_persisted_evidence_corruption(read_runtime, damage):
    from app.models.entities import (
        ChanResearchObservation,
        ChanResearchStreamHead,
        ChanStructureRevision,
    )
    from app.services.chan_read_service import read_latest

    observation = _make_observation()
    publication = _publish(read_runtime.engine, observation)
    with Session(read_runtime.engine) as db:
        if damage == "observation_hash":
            row = db.get(ChanResearchObservation, observation.observation_id)
            row.payload_hash = "0" * 64
        elif damage == "observation_column":
            row = db.get(ChanResearchObservation, observation.observation_id)
            row.input_hash = "0" * 64
        elif damage == "structure_payload":
            row = db.scalar(
                select(ChanStructureRevision).where(
                    ChanStructureRevision.observation_id == observation.observation_id
                )
            )
            row.payload_json = {**row.payload_json, "geometry": {"high": 999.0, "low": 1.0}}
        elif damage == "missing_revision":
            db.execute(
                delete(ChanStructureRevision).where(
                    ChanStructureRevision.observation_id == observation.observation_id
                )
            )
        else:
            head = db.get(ChanResearchStreamHead, publication.stream_id)
            head.latest_sequence_number += 1
        db.commit()

    with Session(read_runtime.engine) as db:
        result = read_latest(db, read_runtime.code, "D")

    assert result["available"] is False
    assert result["reason_code"] == "persistent_evidence_corrupt"
    assert "structures" not in result
    assert "payload_json" not in result


@pytest.mark.parametrize("regression", ["cutoff", "cutoff_at"])
def test_read_latest_fails_closed_when_predecessor_chronology_regresses(read_runtime, regression):
    from app.models.entities import ChanResearchObservation
    from app.services.chan_read_service import read_latest

    first = _make_observation(count=12, revision=f"chronology-first-{regression}")
    latest = _make_observation(count=13, revision=f"chronology-latest-{regression}")
    _publish(read_runtime.engine, first)
    _publish(read_runtime.engine, latest)
    with Session(read_runtime.engine) as db:
        previous = db.get(ChanResearchObservation, first.observation_id)
        payload = dict(previous.payload_json)
        if regression == "cutoff":
            previous.cutoff = latest.cutoff + 1
            payload["cutoff"] = previous.cutoff
        else:
            later_time = latest.cutoff_at + timedelta(days=1)
            previous.cutoff_at = later_time.isoformat()
            payload["cutoff_at"] = previous.cutoff_at
        previous.payload_json = payload
        previous.payload_hash = stable_hash(payload)
        db.commit()

    with Session(read_runtime.engine) as db:
        result = read_latest(db, read_runtime.code, "D")

    assert result["available"] is False
    assert result["reason_code"] == "persistent_evidence_corrupt"


@pytest.mark.parametrize("damage", ["observation_hash", "revision_hash", "transition_reference"])
def test_read_latest_rejects_corrupt_latest_historical_reappearance_witness(read_runtime, damage):
    from app.models.entities import (
        ChanObservedTransition,
        ChanResearchObservation,
        ChanStructureRevision,
    )
    from app.services.chan_read_service import read_latest

    first = _make_observation(revision=f"witness-first-{damage}")
    absent = _make_observation(revision=f"witness-absent-{damage}", with_structure=False)
    reappeared = _make_observation(revision=f"witness-current-{damage}")
    _publish(read_runtime.engine, first)
    _publish(read_runtime.engine, absent)
    _publish(read_runtime.engine, reappeared)

    with Session(read_runtime.engine) as db:
        if damage == "observation_hash":
            witness = db.get(ChanResearchObservation, first.observation_id)
            witness.payload_hash = "0" * 64
        elif damage == "revision_hash":
            witness = db.scalar(
                select(ChanStructureRevision).where(
                    ChanStructureRevision.observation_id == first.observation_id
                )
            )
            witness.payload_hash = "0" * 64
        else:
            witness = db.scalar(
                select(ChanObservedTransition).where(
                    ChanObservedTransition.observation_id == first.observation_id
                )
            )
            witness.revision_id = "0" * 64
        db.commit()

    with Session(read_runtime.engine) as db:
        result = read_latest(db, read_runtime.code, "D")

    assert result["available"] is False
    assert result["reason_code"] == "persistent_evidence_corrupt"


def test_read_latest_bounds_historical_reappearance_witness_query(read_runtime):
    from app.services.chan_read_service import read_latest
    from sqlalchemy import event

    _publish(read_runtime.engine, _make_observation(revision="bounded-witness-first"))
    _publish(read_runtime.engine, _make_observation(revision="bounded-witness-absent", with_structure=False))
    _publish(read_runtime.engine, _make_observation(revision="bounded-witness-current"))
    statements = []

    def capture(_connection, _cursor, statement, _parameters, _context, _executemany):
        if "chan_observed_transitions" in statement and "sequence_number" in statement:
            statements.append(statement.lower())

    event.listen(read_runtime.engine, "before_cursor_execute", capture)
    try:
        with Session(read_runtime.engine) as db:
            result = read_latest(db, read_runtime.code, "D")
    finally:
        event.remove(read_runtime.engine, "before_cursor_execute", capture)

    assert result["available"] is True
    witness_query = next((sql for sql in statements if "limit" in sql), None)
    assert witness_query is not None
    assert "order by" in witness_query


def test_read_latest_transition_view_preserves_unchanged_absent_and_reappearance(read_runtime):
    from app.services.chan_read_service import read_latest

    first = _make_observation(count=12, revision="transition-r1", high=103.0)
    _publish(read_runtime.engine, first)
    with Session(read_runtime.engine) as db:
        first_view = read_latest(db, read_runtime.code, "D")
    assert first_view["transitions"][0]["status"] == "OBSERVED_NEW"

    unchanged = _make_observation(count=13, revision="transition-r2", high=103.0)
    _publish(read_runtime.engine, unchanged)
    with Session(read_runtime.engine) as db:
        unchanged_view = read_latest(db, read_runtime.code, "D")
    assert unchanged_view["transitions"][0]["status"] == "OBSERVED_UNCHANGED"
    assert unchanged_view["transitions"][0]["revision_id"] == unchanged.structures[0].revision_id

    absent = _make_observation(count=14, revision="transition-r3", with_structure=False)
    _publish(read_runtime.engine, absent)
    with Session(read_runtime.engine) as db:
        absent_view = read_latest(db, read_runtime.code, "D")
    assert absent_view["transitions"][0]["status"] == "OBSERVED_ABSENT"
    assert absent_view["transitions"][0]["revision_id"] is None
    assert absent_view["transitions"][0]["prior_revision_id"] == unchanged.structures[0].revision_id

    reappeared = _make_observation(count=15, revision="transition-r4", high=104.0)
    _publish(read_runtime.engine, reappeared)
    with Session(read_runtime.engine) as db:
        reappeared_view = read_latest(db, read_runtime.code, "D")
    assert reappeared_view["transitions"][0]["status"] == "OBSERVED_NEW"
    assert reappeared_view["transitions"][0]["reappearance"] is True


def test_read_latest_fails_closed_on_tampered_transition_status(read_runtime):
    from app.models.entities import ChanObservedTransition
    from app.services.chan_read_service import read_latest

    observation = _make_observation(revision="tampered-transition-status")
    _publish(read_runtime.engine, observation)
    with Session(read_runtime.engine) as db:
        transition = db.scalar(select(ChanObservedTransition).where(
            ChanObservedTransition.observation_id == observation.observation_id
        ))
        transition.status = "OBSERVED_CHANGED"
        db.commit()

    with Session(read_runtime.engine) as db:
        result = read_latest(db, read_runtime.code, "D")

    assert result["available"] is False
    assert result["reason_code"] == "persistent_evidence_corrupt"


def test_read_latest_fails_closed_when_absence_transition_is_missing(read_runtime):
    from app.models.entities import ChanObservedTransition
    from app.services.chan_read_service import read_latest

    first = _make_observation(revision="missing-absence-first")
    absent = _make_observation(revision="missing-absence-next", with_structure=False)
    _publish(read_runtime.engine, first)
    _publish(read_runtime.engine, absent)
    with Session(read_runtime.engine) as db:
        transition = db.scalar(select(ChanObservedTransition).where(
            ChanObservedTransition.observation_id == absent.observation_id
        ))
        assert transition is not None
        db.delete(transition)
        db.commit()

    with Session(read_runtime.engine) as db:
        result = read_latest(db, read_runtime.code, "D")

    assert result["available"] is False
    assert result["reason_code"] == "persistent_evidence_corrupt"


def test_read_latest_fails_closed_when_reappearance_marker_is_tampered(read_runtime):
    from app.models.entities import ChanObservedTransition
    from app.services.chan_read_service import read_latest

    first = _make_observation(revision="tampered-reappearance-first")
    absent = _make_observation(revision="tampered-reappearance-absent", with_structure=False)
    reappeared = _make_observation(revision="tampered-reappearance-current")
    _publish(read_runtime.engine, first)
    _publish(read_runtime.engine, absent)
    _publish(read_runtime.engine, reappeared)
    with Session(read_runtime.engine) as db:
        transition = db.scalar(select(ChanObservedTransition).where(
            ChanObservedTransition.observation_id == reappeared.observation_id
        ))
        transition.reappearance = False
        db.commit()

    with Session(read_runtime.engine) as db:
        result = read_latest(db, read_runtime.code, "D")

    assert result["available"] is False
    assert result["reason_code"] == "persistent_evidence_corrupt"


def test_private_get_auth_interval_cache_and_instrument_boundary(read_runtime):
    from app.core.config import get_settings
    from app.db.session import get_db
    from app.main import app
    from fastapi.testclient import TestClient

    observation = _make_observation()
    _publish(read_runtime.engine, observation)

    def override_get_db():
        with Session(read_runtime.engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/workspace/instruments/{read_runtime.code}/chan?interval=D")
            assert response.status_code == 200
            assert response.headers["cache-control"] == "private, no-store"
            assert response.json()["observation_id"] == observation.observation_id
            assert client.get(f"/api/workspace/instruments/{read_runtime.code}/chan?interval=2h").status_code == 422
            missing = client.get("/api/workspace/instruments/999999.SH/chan")
            unsupported = client.get("/api/workspace/instruments/600000.SH/chan")
            assert missing.status_code == 404
            assert missing.json()["detail"] == "instrument_not_in_catalog"
            assert unsupported.status_code == 404
            assert unsupported.json()["detail"] == "unsupported_instrument_type"

        parameters = app.openapi()["paths"]["/api/workspace/instruments/{code}/chan"]["get"]["parameters"]
        parameter_names = {parameter["name"] for parameter in parameters}
        assert {"code", "interval"} <= parameter_names
        assert not {"as_of", "refresh"} & parameter_names

        auth_settings = get_settings().model_copy(update={"auth_enabled": True})
        app.dependency_overrides[get_settings] = lambda: auth_settings
        with TestClient(app) as client:
            unauthorized = client.get(f"/api/workspace/instruments/{read_runtime.code}/chan")
        assert unauthorized.status_code == 401
    finally:
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_db, None)


def test_private_get_and_kline_compatibility_are_read_only_and_use_persisted_chan(
    read_runtime, monkeypatch
):
    import builtins

    from app.core.config import get_settings
    from app.db.session import get_db
    from app.main import app
    from app.models import ProviderAudit
    from app.models.entities import (
        ChanObservedTransition,
        ChanResearchObservation,
        ChanResearchStreamHead,
        ChanStructureRevision,
    )
    from app.providers import factory
    from app.research import chan_adapter, chan_input
    from app.services.kline_stabilization_service import KlineStabilizationService
    from app.services.task_service import TaskService
    from app.workspace import data_jobs
    from app.workspace.models import WorkspaceDataJob
    from fastapi.testclient import TestClient
    from sqlalchemy import event

    observation = _make_observation()
    _publish(read_runtime.engine, observation)

    def override_get_db():
        with Session(read_runtime.engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    mutation_statements = []

    def record_statement(_conn, _cursor, statement, _parameters, _context, _executemany):
        operation = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else ""
        if operation in {"INSERT", "UPDATE", "DELETE", "REPLACE"}:
            mutation_statements.append(operation)

    event.listen(read_runtime.engine, "before_cursor_execute", record_statement)
    original_import = builtins.__import__

    def reject_legacy_chanlun(name, *args, **kwargs):
        if name == "chanlun" or name.startswith("chanlun."):
            pytest.fail("GET-time legacy chanlun import must be removed")
        if name.split(".", 1)[0] in {"openai", "anthropic", "litellm"}:
            pytest.fail("read GET must not import or call a model gateway")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_legacy_chanlun)
    monkeypatch.setattr(
        chan_input,
        "freeze_chan_input",
        lambda *_args, **_kwargs: pytest.fail("read GET must not freeze Chan input"),
    )
    monkeypatch.setattr(
        chan_adapter.ChanAdapter,
        "observe",
        lambda *_args, **_kwargs: pytest.fail("read GET must not run the engine"),
    )
    monkeypatch.setattr(
        data_jobs,
        "enqueue_chan_structures",
        lambda *_args, **_kwargs: pytest.fail("read GET must not enqueue Chan work"),
    )
    monkeypatch.setattr(
        TaskService,
        "__init__",
        lambda *_args, **_kwargs: pytest.fail("read GET must not construct TaskService"),
    )
    monkeypatch.setattr(
        factory,
        "build_provider",
        lambda *_args, **_kwargs: pytest.fail("read GET must not create a Provider"),
    )

    def table_counts(db):
        return {
            model.__tablename__: db.scalar(select(func.count()).select_from(model))
            for model in (
                ChanResearchObservation,
                ChanStructureRevision,
                ChanObservedTransition,
                ChanResearchStreamHead,
                WorkspaceDataJob,
                ProviderAudit,
            )
        }

    try:
        with Session(read_runtime.engine) as db:
            before = table_counts(db)
        with TestClient(app) as client:
            first = client.get(f"/api/workspace/instruments/{read_runtime.code}/chan?interval=D")
            second = client.get(f"/api/workspace/instruments/{read_runtime.code}/chan?interval=D")
        with Session(read_runtime.engine) as db:
            summary = KlineStabilizationService(settings=get_settings()).summary(db)
            after = table_counts(db)

        assert first.status_code == second.status_code == 200
        assert first.json() == second.json()
        assert first.json()["source"] == "persisted_r4c_observed_revision"
        assert first.json()["provider_called"] is False
        assert first.json()["engine_called"] is False
        assert first.json()["models_called"] is False
        row = next(item for item in summary["rows"] if item["ts_code"] == read_runtime.code)
        assert row["chanlun"]["available"] is True
        assert row["chanlun"]["source"] == "persisted_r4c_observed_revision"
        assert row["chanlun"]["observation_id"] == observation.observation_id
        assert row["chanlun"]["fenxing"] == 1
        assert row["chanlun"]["segments"] is None
        assert row["chanlun"]["engine_confirmation"] == "unknown"
        assert before == after
        assert mutation_statements == []
    finally:
        event.remove(read_runtime.engine, "before_cursor_execute", record_statement)
        app.dependency_overrides.pop(get_db, None)


def test_kline_compatibility_missing_snapshot_stays_unavailable(monkeypatch, read_runtime):
    import builtins

    from app.core.config import get_settings
    from app.services.kline_stabilization_service import KlineStabilizationService

    original_import = builtins.__import__

    def reject_legacy_chanlun(name, *args, **kwargs):
        if name == "chanlun" or name.startswith("chanlun."):
            pytest.fail("missing persisted Chan evidence must not trigger legacy chanlun computation")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_legacy_chanlun)
    with Session(read_runtime.engine) as db:
        row = KlineStabilizationService(settings=get_settings()).summary(db)["rows"][0]

    assert row["chanlun"]["available"] is False
    assert row["chanlun"]["source"] == "persisted_r4c_observed_revision"
    assert row["chanlun"]["reason_code"] == "snapshot_missing"
    assert row["chanlun"]["segments"] is None
    assert row["chanlun"]["engine_confirmation"] == "unknown"


def test_config_removes_only_the_user_facing_read_model_blocker():
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    config = json.loads((root / "config" / "chan_research.json").read_text(encoding="utf-8"))
    assert config["enabled"] is False
    assert config["qualification_status"] == "BLOCKED"
    assert config["selection_status"] == "SELECTED_DISABLED"
    assert "RUNTIME_INTEGRATION_DISABLED" in config["reason_codes"]
    assert "USER_FACING_READ_MODEL_NOT_INTEGRATED" not in config["reason_codes"]

@pytest.fixture
def disposable_m3bc_postgres_runtime(monkeypatch):
    import os
    import subprocess
    import sys
    from contextlib import contextmanager
    from pathlib import Path
    from zoneinfo import ZoneInfo

    from app.core.config import get_settings
    from app.models import DailyBar, Instrument
    from app.services import chan_structure_service
    from app.utils.hashing import stable_hash
    from app.workspace import worker
    from app.workspace.models import WorkspaceDataJob
    from app.workspace.protocol import ChanStructuresJobRequest, content_hash
    from sqlalchemy import text
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import sessionmaker

    database_url = os.getenv("R4C_M3B_C_POSTGRES_URL")
    if not database_url:
        pytest.skip("R4C_M3B_C_POSTGRES_URL is required for disposable PostgreSQL 16 read-model gate")
    parsed = make_url(database_url)
    if (
        parsed.drivername not in {"postgresql+psycopg", "postgresql"}
        or parsed.host not in {"127.0.0.1", "localhost", "::1"}
        or parsed.database != "etf_r4c_m3bc_read_test"
    ):
        pytest.fail("M3B-C PostgreSQL gate only accepts loopback database etf_r4c_m3bc_read_test")

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        server_version = int(connection.execute(text("SHOW server_version_num")).scalar_one())
        existing_tables = connection.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        ).scalars().all()
    if server_version // 10000 != 16 or existing_tables:
        engine.dispose()
        pytest.fail("M3B-C PostgreSQL gate requires a fresh PostgreSQL 16 database")

    project_root = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    environment.update(
        {
            "APP_ENV": "test",
            "AUTH_ENABLED": "false",
            "MARKET_PROVIDER": "mock",
            "ALLOW_MOCK_FALLBACK": "false",
            "AUTO_CREATE_SCHEMA": "false",
            "DATABASE_URL": database_url,
            "ALEMBIC_DATABASE_URL": database_url,
            "PYTHONPATH": str(project_root / "backend"),
        }
    )
    for alembic_args in (("upgrade", "head"), ("check",), ("current",)):
        argv = ["-c", "alembic.ini", *alembic_args]
        completed = subprocess.run(
            [sys.executable, "-c", f"from alembic.config import main; main(argv={argv!r})"],
            cwd=project_root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, f"Alembic {alembic_args[0]} failed: {completed.stdout}{completed.stderr}"

    make_session = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)

    @contextmanager
    def session_scope():
        db = make_session()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    settings = get_settings().model_copy(update={"market_provider": "akshare", "auth_enabled": False})
    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    monkeypatch.setattr(worker, "session_scope", session_scope)
    monkeypatch.setattr(chan_structure_service, "session_scope", session_scope)

    code = "510300.SH"
    with session_scope() as db:
        instrument = Instrument(
            ts_code=code,
            symbol="510300",
            name="Synthetic PostgreSQL ETF",
            kind="ETF",
            exchange="SH",
            enabled=True,
        )
        db.add(instrument)
        db.flush()
        current = datetime(2026, 1, 5).date()
        end = datetime(2027, 1, 29).date()
        offset = 0
        while current <= end:
            if current.weekday() < 5:
                phase = (offset // 5) % 2
                close = 100.0 + (3.0 if phase == 0 else -3.0) + (offset // 50) * 0.2
                open_price = close - 1.0 if phase == 0 else close + 1.0
                db.add(
                    DailyBar(
                        instrument_id=instrument.id,
                        trade_date=current,
                        open=open_price,
                        high=max(open_price, close) + 1.0,
                        low=min(open_price, close) - 1.0,
                        close=close,
                        volume=1000.0 + offset,
                        amount=close * (1000.0 + offset),
                        adjust="none",
                        source="akshare:em:v101",
                        quality_hash=stable_hash({"date": current.isoformat(), "offset": offset}),
                    )
                )
                offset += 1
            current += timedelta(days=1)

    as_of = datetime(2027, 1, 29, 15, 15, tzinfo=ZoneInfo("Asia/Shanghai"))
    request = ChanStructuresJobRequest.model_validate(
        {
            "schema_version": "r4c-chan-job-v1",
            "task": "chan_structures",
            "codes": [code],
            "interval": "D",
            "as_of": as_of,
        }
    )
    job_id = uuid4().hex
    with session_scope() as db:
        db.add(
            WorkspaceDataJob(
                job_id=job_id,
                user_id=None,
                owner_scope="offline-single-user",
                idempotency_key=content_hash({"job": job_id}),
                status="running",
                request_json=request.model_dump(mode="json"),
            )
        )
    assert worker.execute(job_id) == 0
    with session_scope() as db:
        job = db.get(WorkspaceDataJob, job_id)
        result = dict(job.result_json or {})
        status = job.status
    try:
        yield SimpleNamespace(
            engine=engine,
            code=code,
            job_id=job_id,
            result=result,
            status=status,
            server_version=server_version,
            settings=settings,
            session_factory=make_session,
        )
    finally:
        engine.dispose()


def test_postgres16_worker_publication_is_read_by_private_get_without_writes(
    disposable_m3bc_postgres_runtime, monkeypatch
):
    from app.core.config import get_settings
    from app.db.session import get_db
    from app.main import app
    from app.models import ProviderAudit
    from app.models.entities import (
        ChanObservedTransition,
        ChanResearchObservation,
        ChanResearchStreamHead,
        ChanStructureRevision,
    )
    from app.workspace.models import WorkspaceDataJob
    from fastapi.testclient import TestClient
    from sqlalchemy import event

    runtime = disposable_m3bc_postgres_runtime
    assert runtime.server_version // 10000 == 16
    assert runtime.status == "succeeded", runtime.result
    item = runtime.result["items"][0]
    assert item["status"] == "published"
    assert item["structure_counts"]["fx"] > 0

    models = (
        ChanResearchObservation,
        ChanStructureRevision,
        ChanObservedTransition,
        ChanResearchStreamHead,
        WorkspaceDataJob,
        ProviderAudit,
    )

    def table_counts():
        with Session(runtime.engine) as db:
            return {
                model.__tablename__: db.scalar(select(func.count()).select_from(model))
                for model in models
            }

    mutations = []

    def record_statement(_connection, _cursor, statement, _parameters, _context, _executemany):
        operation = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else ""
        if operation in {"INSERT", "UPDATE", "DELETE", "REPLACE"}:
            mutations.append(operation)

    def override_get_db():
        with Session(runtime.engine) as db:
            yield db

    app.dependency_overrides[get_settings] = lambda: runtime.settings
    app.dependency_overrides[get_db] = override_get_db
    event.listen(runtime.engine, "before_cursor_execute", record_statement)
    before = table_counts()
    try:
        with TestClient(app) as client:
            first = client.get(f"/api/workspace/instruments/{runtime.code}/chan?interval=D")
            second = client.get(f"/api/workspace/instruments/{runtime.code}/chan?interval=D")
        after = table_counts()
    finally:
        event.remove(runtime.engine, "before_cursor_execute", record_statement)
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_db, None)

    assert first.status_code == second.status_code == 200
    assert first.headers["cache-control"] == "private, no-store"
    assert first.json() == second.json()
    assert first.json()["observation_id"] == item["observation_id"]
    assert first.json()["available"] is True
    assert first.json()["structures"]
    assert first.json()["counts"]["fx"] > 0
    assert before == after
    assert mutations == []

    from app.services.chan_read_service import read_latest

    event.listen(runtime.engine, "before_cursor_execute", record_statement)
    try:
        for corruption in ("observation", "revision"):
            with runtime.session_factory() as db:
                if corruption == "observation":
                    persisted = db.get(ChanResearchObservation, item["observation_id"])
                    assert persisted is not None
                    persisted.payload_hash = "0" * 64
                else:
                    revision = db.scalar(
                        select(ChanStructureRevision).where(
                            ChanStructureRevision.observation_id == item["observation_id"]
                        )
                    )
                    assert revision is not None
                    revision.payload_hash = "0" * 64
                with db.no_autoflush:
                    corruption_result = read_latest(db, runtime.code, "D")
                db.rollback()
            assert corruption_result["available"] is False
            assert corruption_result["reason_code"] == "persistent_evidence_corrupt"
            assert table_counts() == before
    finally:
        event.remove(runtime.engine, "before_cursor_execute", record_statement)

    assert mutations == []
