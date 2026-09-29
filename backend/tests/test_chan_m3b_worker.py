from __future__ import annotations

import json
import os
import subprocess
import sys
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.db.base import Base
from app.workspace.models import WorkspaceDataJob
from app.workspace.protocol import ChanStructuresJobRequest, ChanStructuresRequest, DataRequest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


def _request_payload(**overrides):
    payload = {
        "schema_version": "r4c-chan-job-v1",
        "task": "chan_structures",
        "codes": ["510500.SH", "510300.SH"],
        "interval": "W",
        "as_of": "2026-09-30T15:15:00+08:00",
        "request_key": uuid4().hex,
    }
    payload.update(overrides)
    return payload


def test_public_data_request_rejects_internal_chan_structures_task():
    with pytest.raises(ValidationError):
        DataRequest.model_validate(
            {
                "task": "chan_structures",
                "request_key": uuid4().hex,
                "codes": ["510300.SH"],
            }
        )


def test_internal_chan_request_canonicalizes_codes_and_normalizes_as_of():
    protocol = import_module("app.workspace.protocol")
    request_type = getattr(protocol, "ChanStructuresRequest", None)
    assert request_type is not None, "internal bounded Chan request contract is not implemented"

    request = request_type.model_validate(_request_payload())
    assert request.schema_version == "r4c-chan-job-v1"
    assert request.task == "chan_structures"
    assert request.codes == ["510300.SH", "510500.SH"]
    assert request.interval == "W"
    assert request.as_of == datetime(2026, 9, 30, 7, 15, tzinfo=UTC)
    assert 16 <= len(request.request_key) <= 64

    persisted_type = getattr(protocol, "ChanStructuresJobRequest", None)
    assert persisted_type is not None, "persisted Chan job request contract is not implemented"
    persisted = persisted_type.model_validate(request.model_dump(mode="json", exclude={"request_key"}))
    assert persisted.codes == request.codes
    assert persisted.as_of == request.as_of


@pytest.mark.parametrize(
    "overrides",
    [
        {"codes": ["510300.SH", "510300.SH"]},
        {"codes": []},
        {"codes": ["not-a-code"]},
        {"interval": "30m"},
        {"as_of": datetime(2026, 9, 30, 15, 15)},
        {"request_key": "short"},
        {"request_key": "a" * 65},
    ],
)
def test_internal_chan_request_rejects_invalid_bounds(overrides):
    protocol = import_module("app.workspace.protocol")
    request_type = getattr(protocol, "ChanStructuresRequest", None)
    assert request_type is not None, "internal bounded Chan request contract is not implemented"
    with pytest.raises(ValidationError):
        request_type.model_validate(_request_payload(**overrides))


def test_internal_chan_request_accepts_thirty_codes_and_rejects_thirty_one():
    codes = [f"{600000 + index:06d}.SH" for index in range(30)]
    request = ChanStructuresRequest.model_validate(_request_payload(codes=codes))
    assert len(request.codes) == 30
    with pytest.raises(ValidationError):
        ChanStructuresRequest.model_validate(_request_payload(codes=[*codes, "600030.SH"]))


@pytest.fixture
def isolated_queue_session(tmp_path):
    # Keep queue/lease tests away from the application test DB and other tests.
    import app.models.entities  # noqa: F401
    import app.workspace.models  # noqa: F401

    engine = create_engine(f"sqlite:///{tmp_path / 'chan-worker-queue.sqlite3'}")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            yield db
    finally:
        engine.dispose()


def _persisted_request(**overrides):
    payload = _request_payload()
    payload.pop("request_key")
    payload.update(overrides)
    return ChanStructuresJobRequest.model_validate(payload)


def test_internal_enqueue_uses_shared_queue_scope_idempotency_and_conflicts(isolated_queue_session):
    data_jobs = import_module("app.workspace.data_jobs")
    enqueue = getattr(data_jobs, "enqueue_chan_structures", None)
    assert callable(enqueue), "internal Chan enqueue helper is not implemented"

    payload = ChanStructuresRequest.model_validate(_request_payload())
    first, created = enqueue(isolated_queue_session, payload)
    assert created is True
    assert first.user_id is None
    assert first.owner_scope == "offline-single-user"
    assert first.request_json == payload.model_dump(mode="json", exclude={"request_key"})

    retry_payload = ChanStructuresRequest.model_validate(
        _request_payload(
            codes=list(reversed(payload.codes)),
            as_of="2026-09-30T07:15:00Z",
            request_key=payload.request_key,
        )
    )
    retry, created = enqueue(isolated_queue_session, retry_payload)
    assert created is False
    assert retry.job_id == first.job_id

    changed = ChanStructuresRequest.model_validate(
        _request_payload(interval="M", request_key=payload.request_key)
    )
    with pytest.raises(data_jobs.WorkspaceError) as error:
        enqueue(isolated_queue_session, changed)
    assert error.value.status == 409
    assert error.value.code == "data_idempotency_conflict"

    ordinary = DataRequest(task="prices", request_key=uuid4().hex)
    ordinary_first, ordinary_created = data_jobs.enqueue(isolated_queue_session, ordinary, None)
    ordinary_retry, ordinary_retry_created = data_jobs.enqueue(isolated_queue_session, ordinary, None)
    assert ordinary_created is True
    assert ordinary_retry_created is False
    assert ordinary_retry.job_id == ordinary_first.job_id
    assert ordinary_first.request_json["task"] == "prices"
    ordinary_conflict = DataRequest(task="quotes", request_key=ordinary.request_key)
    with pytest.raises(data_jobs.WorkspaceError) as ordinary_error:
        data_jobs.enqueue(isolated_queue_session, ordinary_conflict, None)
    assert ordinary_error.value.code == "data_idempotency_conflict"


def test_internal_enqueue_shares_capacity_and_existing_claim_lease_path(isolated_queue_session):
    data_jobs = import_module("app.workspace.data_jobs")
    enqueue = getattr(data_jobs, "enqueue_chan_structures", None)
    assert callable(enqueue), "internal Chan enqueue helper is not implemented"

    now = datetime.now(UTC)
    placeholders = []
    for index in range(9):
        row = WorkspaceDataJob(
            job_id=uuid4().hex,
            user_id=None,
            owner_scope="offline-single-user",
            idempotency_key=f"{index + 1:064x}",
            status="queued",
            request_json={"task": "prices", "codes": []},
        )
        isolated_queue_session.add(row)
        placeholders.append(row)
    isolated_queue_session.flush()

    first_payload = ChanStructuresRequest.model_validate(_request_payload(request_key=uuid4().hex))
    first, created = enqueue(isolated_queue_session, first_payload)
    assert created is True
    assert isolated_queue_session.scalar(
        select(WorkspaceDataJob.job_id).where(WorkspaceDataJob.status == "queued", WorkspaceDataJob.job_id == first.job_id)
    ) == first.job_id

    regular = DataRequest(task="prices", request_key=uuid4().hex)
    with pytest.raises(data_jobs.WorkspaceError) as error:
        data_jobs.enqueue(isolated_queue_session, regular, None)
    assert error.value.status == 429
    assert error.value.code == "data_queue_full"

    # Clear the synthetic capacity rows and prove claim/lease itself still owns
    # scheduling; the helper does not introduce a second worker path.
    for row in placeholders:
        row.status = "failed"
    first.created_at = now - timedelta(hours=2)
    isolated_queue_session.flush()
    second_payload = ChanStructuresRequest.model_validate(_request_payload(request_key=uuid4().hex, interval="D"))
    second, created = enqueue(isolated_queue_session, second_payload)
    assert created is True
    second.created_at = now - timedelta(hours=1)
    isolated_queue_session.flush()
    claimed = data_jobs.claim(isolated_queue_session)
    assert claimed == first.job_id
    assert isolated_queue_session.get(WorkspaceDataJob, first.job_id).status == "running"
    assert isolated_queue_session.get(WorkspaceDataJob, first.job_id).lease_until is not None
    assert data_jobs.claim(isolated_queue_session) is None
    isolated_queue_session.get(WorkspaceDataJob, first.job_id).lease_until = now - timedelta(minutes=1)
    assert data_jobs.claim(isolated_queue_session) == second.job_id
    assert isolated_queue_session.get(WorkspaceDataJob, first.job_id).status == "failed"
    assert isolated_queue_session.get(WorkspaceDataJob, second.job_id).status == "running"


def _prepared_input(instrument: str, interval: str = "D"):
    contract = import_module("app.research.chan_contract")
    return contract.prepare_research_input(
        instrument=instrument,
        interval=interval,
        series_id=f"series-{instrument}-{interval}",
        price_basis_id="basis-raw-v1",
        adjustment_version="none-v1",
        input_revision_id=f"revision-{instrument}-{interval}",
        settlement_status="settled",
        config_id="default-czsc-r4-v1",
        bars=[
            {
                "source_bar_id": f"source-{instrument}-{interval}",
                "timestamp": "2026-09-30T00:00:00+00:00",
                "open": 2.0,
                "high": 2.1,
                "low": 1.9,
                "close": 2.05,
                "volume": 1000,
                "amount": 2050,
            }
        ],
    )


def _request_for(*codes, interval="D"):
    return ChanStructuresJobRequest.model_validate(
        {
            "schema_version": "r4c-chan-job-v1",
            "task": "chan_structures",
            "codes": list(codes),
            "interval": interval,
            "as_of": "2026-09-30T15:15:00+08:00",
        }
    )


def _install_fake_sessions(monkeypatch, module):
    state = {"active": None, "opened": [], "adapter_sessions": [], "publisher_sessions": []}

    class FakeSession:
        def get(self, _model, _key):
            return SimpleNamespace(sequence_number=7)

    @contextmanager
    def fake_session_scope():
        session = FakeSession()
        state["active"] = session
        state["opened"].append(session)
        try:
            yield session
        finally:
            state["active"] = None

    monkeypatch.setattr(module, "session_scope", fake_session_scope)
    return state


def test_structure_service_skips_engine_and_publication_for_blocked_input(monkeypatch):
    from app.research.chan_input import FrozenChanInput
    from app.services import chan_structure_service as module

    state = _install_fake_sessions(monkeypatch, module)
    monkeypatch.setattr(
        module,
        "freeze_chan_input",
        lambda *_args, **_kwargs: FrozenChanInput(
            status="blocked", reason_code="history_qualification_blocked", detail_code="mock_history"
        ),
    )

    class UnexpectedAdapter:
        def observe(self, _prepared):
            pytest.fail("blocked Chan input must not initialize or invoke CZSC")

    class UnexpectedPublisher:
        def __init__(self, _session):
            pytest.fail("blocked Chan input must not publish")

    monkeypatch.setattr(module, "ChanObservationPublisher", UnexpectedPublisher)
    status, result = module.ChanStructureService(settings=SimpleNamespace(), adapter=UnexpectedAdapter()).run(
        _request_for("510300.SH")
    )
    assert status == "partial"
    assert result["items"] == [
        {
            "ts_code": "510300.SH",
            "interval": "D",
            "status": "blocked",
            "reason_code": "history_qualification_blocked",
        }
    ]
    assert result["provider_called"] is False
    assert result["models_called"] is False
    assert result["qualification_changed"] is False
    assert result["actionable"] is False
    assert len(state["opened"]) == 1


def test_structure_service_closes_freeze_before_compute_and_publishes_in_new_transaction(monkeypatch):
    from app.research.chan_input import FrozenChanInput
    from app.services import chan_structure_service as module

    state = _install_fake_sessions(monkeypatch, module)
    prepared = _prepared_input("510300.SH")
    observation = import_module("app.research.chan_contract").make_observation(prepared, [])
    freeze_sessions = []
    publish_sessions = []

    def freeze(db, _settings, code, *, interval, as_of):
        assert db is state["active"]
        assert code == "510300.SH"
        assert interval == "D"
        assert as_of == datetime(2026, 9, 30, 7, 15, tzinfo=UTC)
        freeze_sessions.append(db)
        return FrozenChanInput(status="prepared", prepared=prepared, price_basis_id="basis-raw-v1")

    class Adapter:
        def observe(self, value):
            assert value is prepared
            assert state["active"] is None, "CZSC must run after the freeze transaction closes"
            state["adapter_sessions"].append(tuple(state["opened"]))
            return observation

    class Publisher:
        def __init__(self, db):
            assert db is state["active"]
            publish_sessions.append(db)

        def publish(self, value):
            assert value is observation
            return SimpleNamespace(already_published=False)

    monkeypatch.setattr(module, "freeze_chan_input", freeze)
    monkeypatch.setattr(module, "ChanObservationPublisher", Publisher)
    status, result = module.ChanStructureService(settings=SimpleNamespace(), adapter=Adapter()).run(
        _request_for("510300.SH")
    )

    item = result["items"][0]
    assert status == "succeeded"
    assert item["status"] == "published"
    assert item["observation_id"] == observation.observation_id
    assert item["input_hash"] == observation.input_hash
    assert item["publication_sequence"] == 7
    assert item["already_published"] is False
    assert item["structure_counts"] == {"fx": 0, "bi": 0, "zs": 0}
    assert freeze_sessions[0] is not publish_sessions[0]
    assert len(state["opened"]) == 2


def test_structure_service_isolates_code_failures_and_bounds_idempotent_results(monkeypatch):
    from app.research.chan_adapter import ChanAdapterError
    from app.research.chan_input import FrozenChanInput
    from app.services import chan_structure_service as module

    state = _install_fake_sessions(monkeypatch, module)
    prepared_by_code = {code: _prepared_input(code) for code in ("510300.SH", "510500.SH", "510700.SH")}
    observations = {
        code: import_module("app.research.chan_contract").make_observation(prepared, [])
        for code, prepared in prepared_by_code.items()
    }

    def freeze(_db, _settings, code, *, interval, as_of):
        assert state["active"] is not None
        assert interval == "D"
        return FrozenChanInput(status="prepared", prepared=prepared_by_code[code], price_basis_id="basis-raw-v1")

    class Adapter:
        def observe(self, prepared):
            assert state["active"] is None
            state["adapter_sessions"].append(prepared.instrument)
            if prepared.instrument == "510700.SH":
                raise ChanAdapterError("unsupported_engine_version", "private details must not persist")
            return observations[prepared.instrument]

    class Publisher:
        def __init__(self, db):
            assert state["active"] is db
            state["publisher_sessions"].append(db)

        def publish(self, observation):
            return SimpleNamespace(already_published=observation.instrument == "510500.SH")

    monkeypatch.setattr(module, "freeze_chan_input", freeze)
    monkeypatch.setattr(module, "ChanObservationPublisher", Publisher)
    status, result = module.ChanStructureService(settings=SimpleNamespace(), adapter=Adapter()).run(
        _request_for("510700.SH", "510300.SH", "510500.SH")
    )

    assert status == "partial"
    assert [item["status"] for item in result["items"]] == ["published", "idempotent", "failed"]
    assert result["items"][1]["already_published"] is True
    assert result["items"][2]["reason_code"] == "unsupported_engine_version"
    assert "private details" not in str(result)
    allowed = {
        "ts_code", "interval", "status", "observation_id", "input_hash", "publication_sequence",
        "already_published", "structure_counts", "reason_code",
    }
    assert all(set(item).issubset(allowed) for item in result["items"])
    assert result["provider_called"] is False
    assert result["models_called"] is False
    assert result["qualification_changed"] is False
    assert result["actionable"] is False
    assert state["adapter_sessions"] == ["510300.SH", "510500.SH", "510700.SH"]
    assert len(state["publisher_sessions"]) == 2


def test_worker_dispatches_chan_before_runtime_resolution_and_task_or_provider_construction(monkeypatch):
    from app.services.runtime_service import RuntimeService
    from app.workspace import worker

    request = _persisted_request()
    row = SimpleNamespace(
        status="running",
        request_json=request.model_dump(mode="json"),
        user_id=None,
        result_json=None,
        failure_reason=None,
        finished_at=None,
    )

    class FakeDB:
        def get(self, _model, key):
            return row if key == "chan-job" else None

    @contextmanager
    def fake_session_scope():
        yield FakeDB()

    expected_result = {
        "items": [],
        "provider_called": False,
        "models_called": False,
        "qualification_changed": False,
        "actionable": False,
    }

    class FakeChanService:
        def __init__(self, settings):
            self.settings = settings

        def run(self, value):
            assert isinstance(value, ChanStructuresJobRequest)
            return "partial", expected_result

    monkeypatch.setattr(worker, "session_scope", fake_session_scope)
    monkeypatch.setattr(worker, "TaskService", lambda *_args, **_kwargs: pytest.fail("ordinary TaskService must not be built"))
    monkeypatch.setattr(RuntimeService, "resolve_settings", lambda *_args, **_kwargs: pytest.fail("Chan does not resolve provider settings"))
    monkeypatch.setattr("app.services.chan_structure_service.ChanStructureService", FakeChanService)

    assert worker.execute("chan-job") == 0
    assert row.status == "partial"
    assert row.result_json == expected_result
    assert row.failure_reason is None
    assert row.finished_at is not None


def test_worker_keeps_existing_prices_task_service_route(monkeypatch):
    from app.core.config import get_settings
    from app.services.runtime_service import RuntimeService
    from app.workspace import worker

    settings = get_settings()
    request = DataRequest(task="prices", request_key=uuid4().hex)
    row = SimpleNamespace(
        status="running",
        request_json=request.model_dump(mode="json"),
        user_id=None,
        result_json=None,
        failure_reason=None,
        finished_at=None,
    )
    calls = {"constructed": 0, "tasks": []}

    class FakeDB:
        def get(self, _model, _key):
            return row

        def scalar(self, _statement):
            return 1

    @contextmanager
    def fake_session_scope():
        yield FakeDB()

    class FakeTaskService:
        def __init__(self, received_settings):
            assert received_settings.analysis_enabled is False
            assert received_settings.llm_enabled is False
            calls["constructed"] += 1

        def run(self, _db, name, **kwargs):
            calls["tasks"].append((name, kwargs))
            return {"status": "succeeded", "count": 1}

        def close(self):
            return None

    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    monkeypatch.setattr(worker, "session_scope", fake_session_scope)
    monkeypatch.setattr(worker, "TaskService", FakeTaskService)
    monkeypatch.setattr(worker, "task_sequence", lambda *_args: [("refresh_quotes", {"codes": ["510300.SH"]})])
    monkeypatch.setattr(RuntimeService, "resolve_settings", lambda *_args, **_kwargs: settings)

    assert worker.execute("prices-job") == 0, (row.failure_reason, row.result_json)
    assert calls["constructed"] == 1
    assert calls["tasks"] == [("refresh_quotes", {"codes": ["510300.SH"]})]
    assert row.status == "succeeded"
    assert row.failure_reason is None


@pytest.fixture
def isolated_worker_runtime(tmp_path, monkeypatch):
    import app.models.entities  # noqa: F401
    from app.core.config import get_settings
    from app.models import DailyBar, Instrument
    from app.services import chan_structure_service
    from app.utils.hashing import stable_hash
    from app.workspace import worker
    from app.workspace.protocol import content_hash
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{tmp_path / 'chan-worker-runtime.sqlite3'}")
    Base.metadata.create_all(engine)
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

    settings = get_settings().model_copy(update={"market_provider": "akshare"})
    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    monkeypatch.setattr(worker, "session_scope", session_scope)
    monkeypatch.setattr(chan_structure_service, "session_scope", session_scope)

    code = "510300.SH"
    with session_scope() as db:
        instrument = Instrument(
            ts_code=code,
            symbol="510300",
            name="Synthetic ETF",
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

    def run_job(interval: str, as_of: datetime, *, request_key: str | None = None):
        request = ChanStructuresJobRequest.model_validate(
            {
                "schema_version": "r4c-chan-job-v1",
                "task": "chan_structures",
                "codes": [code],
                "interval": interval,
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
        if request_key is not None:
            assert 16 <= len(request_key) <= 64
        assert worker.execute(job_id) == 0
        with session_scope() as db:
            row = db.get(WorkspaceDataJob, job_id)
            return row.status, dict(row.result_json or {})

    try:
        yield SimpleNamespace(engine=engine, run_job=run_job, code=code)
    finally:
        engine.dispose()


def test_worker_publishes_synthetic_d_w_m_and_preserves_immutable_chronology(isolated_worker_runtime):
    from importlib.metadata import PackageNotFoundError, version

    from app.models.entities import ChanResearchObservation, ChanResearchStreamHead
    from app.research.chan_contract import ENGINE_VERSION
    from sqlalchemy import func

    try:
        installed = version("czsc")
    except PackageNotFoundError:
        pytest.skip("pinned CZSC integration runs in the dedicated Python 3.12 environment")
    assert installed == ENGINE_VERSION == "1.0.1"

    runtime = isolated_worker_runtime
    shanghai = datetime.fromisoformat("2026-01-14T15:15:00+08:00").tzinfo
    wednesday = datetime(2026, 1, 14, 15, 15, tzinfo=shanghai)
    friday = datetime(2026, 1, 16, 15, 15, tzinfo=shanghai)

    wednesday_status, wednesday_result = runtime.run_job("W", wednesday)
    assert wednesday_status == "succeeded", wednesday_result
    wednesday_item = wednesday_result["items"][0]
    assert wednesday_item["status"] == "published"

    friday_status, friday_result = runtime.run_job("W", friday)
    assert friday_status == "succeeded", friday_result
    friday_item = friday_result["items"][0]
    assert friday_item["status"] == "published"
    assert friday_item["publication_sequence"] == wednesday_item["publication_sequence"] + 1

    retry_status, retry_result = runtime.run_job("W", friday)
    assert retry_status == "succeeded", retry_result
    retry_item = retry_result["items"][0]
    assert retry_item["status"] == "idempotent"
    assert retry_item["observation_id"] == friday_item["observation_id"]
    assert retry_item["publication_sequence"] == friday_item["publication_sequence"]

    rewind_status, rewind_result = runtime.run_job("W", datetime(2026, 1, 9, 15, 15, tzinfo=shanghai))
    assert rewind_status == "failed", rewind_result
    assert rewind_result["items"][0]["reason_code"] == "observation_order_reversed"

    d_status, d_result = runtime.run_job("D", datetime(2026, 1, 30, 15, 15, tzinfo=shanghai))
    m_status, m_result = runtime.run_job("M", datetime(2027, 1, 29, 15, 15, tzinfo=shanghai))
    assert d_status == "succeeded", d_result
    assert m_status == "succeeded", m_result
    assert d_result["items"][0]["status"] == "published"
    assert m_result["items"][0]["status"] == "published"
    assert d_result["items"][0]["structure_counts"]["fx"] > 0

    with Session(runtime.engine) as db:
        weekly = list(
            db.scalars(
                select(ChanResearchObservation)
                .where(ChanResearchObservation.instrument == runtime.code, ChanResearchObservation.interval == "W")
                .order_by(ChanResearchObservation.sequence_number)
            )
        )
        assert len(weekly) == 2
        assert weekly[0].settlement_status == "temporary"
        assert weekly[1].settlement_status == "settled"
        assert weekly[0].observation_id == wednesday_item["observation_id"]
        assert weekly[1].observation_id == friday_item["observation_id"]
        assert weekly[1].sequence_number == friday_item["publication_sequence"]
        head = db.get(ChanResearchStreamHead, weekly[0].stream_id)
        assert head.latest_observation_id == friday_item["observation_id"]
        assert db.scalar(
            select(func.count()).select_from(ChanResearchObservation).where(ChanResearchObservation.interval == "D")
        ) == 1
        assert db.scalar(
            select(func.count()).select_from(ChanResearchObservation).where(ChanResearchObservation.interval == "M")
        ) == 1

    assert all(
        flag is False
        for result in (wednesday_result, friday_result, retry_result, d_result, m_result)
        for flag in (
            result["provider_called"],
            result["models_called"],
            result["qualification_changed"],
            result["actionable"],
        )
    )

    from app.workspace.protocol import content_hash

    semantic = {
        "D": d_result["items"][0],
        "W_temporary": wednesday_item,
        "W_settled": friday_item,
        "W_retry": retry_item,
        "M": m_result["items"][0],
    }
    print(
        "R4C_M3B_B_EXACT_ENGINE="
        + json.dumps(
            {
                "python": sys.version.split()[0],
                "czsc": installed,
                "platform": sys.platform,
                "semantic": semantic,
                "semantic_digest": content_hash(semantic),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


@pytest.fixture
def disposable_postgres16_runtime(monkeypatch):
    """Use only the fresh loopback PostgreSQL database named by M3B-B."""
    from app.core.config import get_settings
    from app.models import DailyBar, Instrument
    from app.services import chan_structure_service
    from app.utils.hashing import stable_hash
    from app.workspace import worker
    from app.workspace.protocol import content_hash
    from sqlalchemy import text
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import sessionmaker

    database_url = os.getenv("R4C_M3_POSTGRES_URL")
    if not database_url:
        pytest.skip("R4C_M3_POSTGRES_URL is required for the disposable PostgreSQL 16 worker gate")
    parsed = make_url(database_url)
    if (
        parsed.drivername not in {"postgresql+psycopg", "postgresql"}
        or parsed.host not in {"127.0.0.1", "localhost", "::1"}
        or parsed.database != "etf_r4c_m3_test"
    ):
        pytest.fail("PostgreSQL worker gate only accepts loopback database etf_r4c_m3_test")

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        server_version = int(connection.execute(text("SHOW server_version_num")).scalar_one())
        existing_tables = connection.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        ).scalars().all()
    if server_version // 10000 != 16 or existing_tables:
        engine.dispose()
        pytest.fail("PostgreSQL worker gate requires a fresh PostgreSQL 16 database")

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
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                f"from alembic.config import main; main(argv=['-c','alembic.ini',{','.join(repr(arg) for arg in alembic_args)}])",
            ],
            cwd=project_root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, f"Alembic {alembic_args[0]} failed"

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

    settings = get_settings().model_copy(update={"market_provider": "akshare"})
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

    def run_job(interval: str, as_of: datetime):
        request = ChanStructuresJobRequest.model_validate(
            {
                "schema_version": "r4c-chan-job-v1",
                "task": "chan_structures",
                "codes": [code],
                "interval": interval,
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
            row = db.get(WorkspaceDataJob, job_id)
            return row.status, dict(row.result_json or {})

    try:
        yield SimpleNamespace(engine=engine, run_job=run_job, code=code, server_version=server_version)
    finally:
        engine.dispose()


def test_postgres16_worker_retry_and_chronology_failure_preserve_immutable_head(disposable_postgres16_runtime):
    import platform

    from app.models.entities import ChanResearchObservation, ChanResearchStreamHead
    from app.research.chan_contract import ENGINE_VERSION
    from sqlalchemy import func

    runtime = disposable_postgres16_runtime
    assert runtime.server_version // 10000 == 16
    assert import_module("importlib.metadata").version("czsc") == ENGINE_VERSION == "1.0.1"
    shanghai = datetime.fromisoformat("2026-01-16T15:15:00+08:00").tzinfo

    first_status, first_result = runtime.run_job("W", datetime(2026, 1, 16, 15, 15, tzinfo=shanghai))
    assert first_status == "succeeded", first_result
    first_item = first_result["items"][0]
    assert first_item["status"] == "published"
    assert first_item["publication_sequence"] == 1

    retry_status, retry_result = runtime.run_job("W", datetime(2026, 1, 16, 15, 15, tzinfo=shanghai))
    assert retry_status == "succeeded", retry_result
    retry_item = retry_result["items"][0]
    assert retry_item["status"] == "idempotent"
    assert retry_item["observation_id"] == first_item["observation_id"]
    assert retry_item["publication_sequence"] == first_item["publication_sequence"]

    older_status, older_result = runtime.run_job("W", datetime(2026, 1, 9, 15, 15, tzinfo=shanghai))
    assert older_status == "failed", older_result
    assert older_result["items"][0]["reason_code"] == "observation_order_reversed"

    with Session(runtime.engine) as db:
        observations = list(
            db.scalars(
                select(ChanResearchObservation).where(
                    ChanResearchObservation.instrument == runtime.code,
                    ChanResearchObservation.interval == "W",
                )
            )
        )
        assert len(observations) == 1
        assert observations[0].observation_id == first_item["observation_id"]
        assert observations[0].sequence_number == first_item["publication_sequence"]
        head = db.get(ChanResearchStreamHead, observations[0].stream_id)
        assert head.latest_observation_id == first_item["observation_id"]
        assert db.scalar(
            select(func.count()).select_from(ChanResearchObservation).where(
                ChanResearchObservation.interval == "W"
            )
        ) == 1

    from app.workspace.protocol import content_hash

    semantic = {"first": first_item, "retry": retry_item, "chronology_rejection": older_result["items"][0]}
    print(
        "R4C_M3B_B_POSTGRES16="
        + json.dumps(
            {
                "python": platform.python_version(),
                "czsc": ENGINE_VERSION,
                "postgresql_major": runtime.server_version // 10000,
                "semantic": semantic,
                "semantic_digest": content_hash(semantic),
                "provider_called": first_result["provider_called"],
                "models_called": first_result["models_called"],
                "qualification_changed": first_result["qualification_changed"],
                "actionable": first_result["actionable"],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
