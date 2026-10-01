from __future__ import annotations

import importlib
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from importlib.util import find_spec
from pathlib import Path
from threading import Barrier

import pytest
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _module(name: str):
    spec = find_spec(name)
    assert spec is not None, f"M3 persistence module is not implemented: {name}"
    return importlib.import_module(name)


def _rows(count: int = 40) -> list[dict[str, object]]:
    start = date(2026, 1, 5)
    rows: list[dict[str, object]] = []
    for index in range(count):
        phase = (index // 5) % 2
        close = 100.0 + (3.0 if phase == 0 else -3.0)
        open_price = close - 1.0 if phase == 0 else close + 1.0
        rows.append(
            {
                "source_bar_id": f"bar-{index:04d}",
                "timestamp": start + timedelta(days=index),
                "open": open_price,
                "high": max(open_price, close) + 1.0,
                "low": min(open_price, close) - 1.0,
                "close": close,
                "volume": 100.0,
                "amount": 100.0 * close,
            }
        )
    return rows


def _observation(*, input_revision: str, high: float | None = 103.0, **overrides):
    contract = _module("app.research.chan_contract")
    values = {
        "instrument": "510300.SH",
        "interval": "D",
        "series_id": "series-510300-raw-r1",
        "price_basis_id": "basis-raw-v1",
        "adjustment_version": "none-v1",
        "input_revision_id": input_revision,
        "settlement_status": "settled",
        "config_id": "default-czsc-r4-v1",
        "bars": _rows(),
    }
    values.update(overrides)
    prepared = contract.prepare_research_input(**values)
    structures = []
    if high is not None:
        structures.append(
            contract.build_structure_evidence(
                prepared,
                observation_id=contract.build_observation_id(prepared),
                kind="fx",
                direction=None,
                mark="顶分型",
                source_start=str(prepared.bars[10].timestamp),
                source_end=str(prepared.bars[10].timestamp),
                source_start_bar_id=prepared.bars[10].source_bar_id,
                source_end_bar_id=prepared.bars[10].source_bar_id,
                geometry={"high": high, "low": 101.0},
                engine_state=None,
            )
        )
    return contract.make_observation(prepared, structures)


def _alembic(database_url: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(
        {
            "APP_ENV": "test",
            "AUTH_ENABLED": "false",
            "MARKET_PROVIDER": "mock",
            "AUTO_CREATE_SCHEMA": "false",
            "DATABASE_URL": database_url,
            "ALEMBIC_DATABASE_URL": database_url,
            "PYTHONPATH": str(PROJECT_ROOT / "backend"),
        }
    )
    args = ["-c", "alembic.ini", *arguments]
    return subprocess.run(
        [sys.executable, "-c", f"from alembic.config import main; main(argv={args!r})"],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture(scope="module")
def migrated_engine(tmp_path_factory):
    database_path = tmp_path_factory.mktemp("chan-m3") / "isolated.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    upgrade = _alembic(database_url, "upgrade", "head")
    assert upgrade.returncode == 0, upgrade.stderr
    heads = _alembic(database_url, "heads")
    assert heads.returncode == 0 and "h9c0d1e2f3a4" in (heads.stdout + heads.stderr)
    current = _alembic(database_url, "current")
    assert current.returncode == 0 and "h9c0d1e2f3a4" in (current.stdout + current.stderr)
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(migrated_engine):
    connection = migrated_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


def test_m3_alembic_schema_has_four_tables_constraints_and_append_only_triggers(migrated_engine):
    names = set(inspect(migrated_engine).get_table_names())
    assert {
        "chan_research_observations",
        "chan_structure_revisions",
        "chan_observed_transitions",
        "chan_research_stream_heads",
    } <= names
    with migrated_engine.connect() as connection:
        triggers = {
            row[0]
            for row in connection.execute(
                text("SELECT name FROM sqlite_master WHERE type='trigger'")
            )
        }
    for table in ("chan_research_observations", "chan_structure_revisions", "chan_observed_transitions"):
        assert f"trg_{table}_no_update" in triggers
        assert f"trg_{table}_no_delete" in triggers
    assert "trg_chan_research_stream_heads_no_delete" in triggers


def test_publisher_matches_m2_replay_for_same_day_revisions_absence_and_reappearance(db_session):
    replay = _module("app.research.chan_replay").ObservedRevisionReplay()
    publisher = _module("app.services.chan_observation_service").ChanObservationPublisher(db_session)
    observations = [
        _observation(input_revision="input-r1", high=103.0),
        _observation(input_revision="input-r2", high=104.0),
        _observation(input_revision="input-r3", high=None),
        _observation(input_revision="input-r4", high=105.0),
    ]
    for observation in observations:
        expected = replay.append(observation)
        actual = publisher.publish(observation)
        assert actual.already_published is False
        assert actual.transitions == expected
    assert [item.status for item in replay.history] == [
        "OBSERVED_NEW",
        "OBSERVED_CHANGED",
        "OBSERVED_ABSENT",
        "OBSERVED_NEW",
    ]
    assert replay.history[-1].reappearance is True


def test_exact_retry_is_idempotent_but_same_observation_id_with_changed_evidence_fails_closed(db_session):
    publisher = _module("app.services.chan_observation_service").ChanObservationPublisher(db_session)
    observation = _observation(input_revision="input-r1", high=103.0)
    first = publisher.publish(observation)
    retry = publisher.publish(observation)
    assert first.already_published is False
    assert retry.already_published is True
    assert retry.transitions == ()

    conflicting = _observation(input_revision="input-r1", high=106.0)
    assert conflicting.observation_id == observation.observation_id
    with pytest.raises(_module("app.research.chan_contract").ChanContractError) as exc:
        publisher.publish(conflicting)
    assert exc.value.code == "observation_id_conflict"


def test_failed_atomic_publication_leaves_no_observation_revision_transition_or_head(db_session):
    entities = _module("app.models.entities")
    publisher = _module("app.services.chan_observation_service").ChanObservationPublisher(db_session)

    def reject_head(mapper, connection, target):
        del mapper, connection, target
        raise RuntimeError("injected head publication failure")

    from sqlalchemy import event

    event.listen(entities.ChanResearchStreamHead, "before_insert", reject_head)
    try:
        with pytest.raises(RuntimeError, match="injected head publication failure"):
            publisher.publish(_observation(input_revision="input-r1", high=103.0))
    finally:
        event.remove(entities.ChanResearchStreamHead, "before_insert", reject_head)
        db_session.rollback()
    assert db_session.scalar(select(entities.ChanResearchObservation)) is None
    assert db_session.scalar(select(entities.ChanStructureRevision)) is None
    assert db_session.scalar(select(entities.ChanObservedTransition)) is None
    assert db_session.scalar(select(entities.ChanResearchStreamHead)) is None


def test_migrated_evidence_tables_reject_raw_sql_update_and_delete(db_session):
    publisher = _module("app.services.chan_observation_service").ChanObservationPublisher(db_session)
    publisher.publish(_observation(input_revision="input-r1", high=103.0))
    db_session.flush()

    for table in (
        "chan_research_observations",
        "chan_structure_revisions",
        "chan_observed_transitions",
    ):
        for statement in (
            f"UPDATE {table} SET stream_id = stream_id",
            f"DELETE FROM {table}",
        ):
            with pytest.raises(IntegrityError):
                with db_session.begin_nested():
                    db_session.execute(text(statement))

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.execute(text("DELETE FROM chan_research_stream_heads"))

    head_stream_id = db_session.scalar(text("SELECT stream_id FROM chan_research_stream_heads LIMIT 1"))
    assert head_stream_id is not None
    with db_session.begin_nested():
        db_session.execute(
            text(
                "UPDATE chan_research_stream_heads "
                "SET latest_sequence_number = latest_sequence_number, "
                "latest_observation_id = latest_observation_id WHERE stream_id = :stream_id"
            ),
            {"stream_id": head_stream_id},
        )
    for statement in (
        "UPDATE chan_research_stream_heads SET stream_id = 'tampered' WHERE stream_id = :stream_id",
        "UPDATE chan_research_stream_heads SET config_id = 'tampered' WHERE stream_id = :stream_id",
        "UPDATE chan_research_stream_heads SET instrument = 'tampered' WHERE stream_id = :stream_id",
    ):
        with pytest.raises(IntegrityError):
            with db_session.begin_nested():
                db_session.execute(text(statement), {"stream_id": head_stream_id})


def test_price_basis_and_config_namespaces_are_separate_persistent_streams(db_session):
    entities = _module("app.models.entities")
    publisher = _module("app.services.chan_observation_service").ChanObservationPublisher(db_session)
    raw = _observation(input_revision="input-r1", high=103.0)
    adjusted = _observation(input_revision="input-r1", high=103.0, price_basis_id="basis-split-v1")
    other_config = _observation(input_revision="input-r1", high=103.0, config_id="other-czsc-config-v1")
    publisher.publish(raw)
    publisher.publish(adjusted)
    publisher.publish(other_config)
    heads = list(db_session.scalars(select(entities.ChanResearchStreamHead)))
    assert len(heads) == 3
    assert {head.price_basis_id for head in heads} == {"basis-raw-v1", "basis-split-v1"}
    assert {head.config_id for head in heads} == {"default-czsc-r4-v1", "other-czsc-config-v1"}


def test_empty_complete_observation_persists_without_false_absence(db_session):
    entities = _module("app.models.entities")
    publisher = _module("app.services.chan_observation_service").ChanObservationPublisher(db_session)
    empty = _observation(input_revision="input-r1", high=None)
    first = publisher.publish(empty)
    assert first.transitions == ()
    assert first.already_published is False

    present = _observation(input_revision="input-r2", high=103.0)
    second = publisher.publish(present)
    assert [(item.status, item.reappearance) for item in second.transitions] == [("OBSERVED_NEW", False)]
    assert db_session.get(entities.ChanResearchObservation, empty.observation_id) is not None
    assert db_session.scalar(
        select(entities.ChanObservedTransition).where(
            entities.ChanObservedTransition.observation_id == empty.observation_id
        )
    ) is None


def test_backward_cutoff_is_rejected_and_head_cannot_be_rewound(db_session):
    entities = _module("app.models.entities")
    contract = _module("app.research.chan_contract")
    publisher = _module("app.services.chan_observation_service").ChanObservationPublisher(db_session)
    first = _observation(input_revision="input-r1", high=103.0)
    publisher.publish(first)

    earlier = _observation(input_revision="input-r2", bars=_rows(39), high=104.0)
    with pytest.raises(contract.ChanContractError) as exc:
        publisher.publish(earlier)
    assert exc.value.code == "observation_order_reversed"

    later = _observation(input_revision="input-r3", high=104.0)
    publisher.publish(later)
    head = db_session.scalar(select(entities.ChanResearchStreamHead))
    assert head is not None and head.latest_observation_id == later.observation_id
    first_row = db_session.get(entities.ChanResearchObservation, first.observation_id)
    assert first_row is not None and first_row.sequence_number == 1
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.execute(
                text(
                    "UPDATE chan_research_stream_heads "
                    "SET latest_sequence_number = :sequence_number, latest_observation_id = :observation_id "
                    "WHERE stream_id = :stream_id"
                ),
                {
                    "sequence_number": first_row.sequence_number,
                    "observation_id": first.observation_id,
                    "stream_id": head.stream_id,
                },
            )


def test_config_removes_only_m3_persistence_blocker_after_remote_pass():
    root = Path(__file__).resolve().parents[2]
    config = __import__("json").loads((root / "config" / "chan_research.json").read_text(encoding="utf-8"))
    assert config["enabled"] is False
    assert config["qualification_status"] == "BLOCKED"
    assert config["selection_status"] == "SELECTED_DISABLED"
    assert config["selection_contract"]["engine_confirmation"] == "unknown"
    assert config["reason_codes"] == [
        "RUNTIME_INTEGRATION_DISABLED",
    ]


@pytest.fixture(scope="module")
def migrated_postgres_engine():
    database_url = os.getenv("R4C_M3_POSTGRES_URL")
    if not database_url:
        pytest.skip("set R4C_M3_POSTGRES_URL to a disposable PostgreSQL 16 database")
    parsed = make_url(database_url)
    if parsed.drivername not in {"postgresql+psycopg", "postgresql"}:
        pytest.fail("R4C_M3_POSTGRES_URL must use PostgreSQL/psycopg")
    if parsed.host not in {"127.0.0.1", "localhost", "::1"} or parsed.database != "etf_r4c_m3_test":
        pytest.fail("R4C_M3_POSTGRES_URL must point at the loopback disposable database etf_r4c_m3_test")
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        version = int(connection.execute(text("SHOW server_version_num")).scalar_one())
        existing_tables = connection.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        ).scalars().all()
    if version // 10000 != 16:
        engine.dispose()
        pytest.fail("R4C M3 concurrency qualification requires PostgreSQL 16")
    if existing_tables:
        engine.dispose()
        pytest.fail("R4C_M3_POSTGRES_URL must point at a fresh disposable database")
    upgrade = _alembic(database_url, "upgrade", "head")
    assert upgrade.returncode == 0, upgrade.stderr
    check = _alembic(database_url, "check")
    assert check.returncode == 0, check.stderr
    downgrade = _alembic(database_url, "downgrade", "base")
    assert downgrade.returncode == 0, downgrade.stderr
    reupgrade = _alembic(database_url, "upgrade", "head")
    assert reupgrade.returncode == 0, reupgrade.stderr
    recheck = _alembic(database_url, "check")
    assert recheck.returncode == 0, recheck.stderr
    heads = _alembic(database_url, "heads")
    assert heads.returncode == 0 and "h9c0d1e2f3a4" in (heads.stdout + heads.stderr)
    current = _alembic(database_url, "current")
    assert current.returncode == 0 and "h9c0d1e2f3a4" in (current.stdout + current.stderr)
    try:
        yield engine
    finally:
        engine.dispose()


def test_postgres_16_concurrent_publication_is_serialized_and_history_is_immutable(migrated_postgres_engine):
    entities = _module("app.models.entities")
    observations = [_observation(input_revision="input-r1", high=103.0)] * 2
    start = Barrier(2)

    def publish(observation):
        with Session(migrated_postgres_engine, expire_on_commit=False) as session:
            with session.begin():
                start.wait(timeout=15)
                return _module("app.services.chan_observation_service").ChanObservationPublisher(session).publish(
                    observation
                )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(publish, observations))
    assert sorted(result.already_published for result in results) == [False, True]

    revisions = [
        _observation(input_revision="input-r2", high=104.0),
        _observation(input_revision="input-r3", high=105.0),
    ]
    start = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        changed = list(executor.map(publish, revisions))
    assert all(not result.already_published for result in changed)

    with Session(migrated_postgres_engine) as session:
        assert session.scalar(select(func.count()).select_from(entities.ChanResearchObservation)) == 3
        assert session.scalar(select(func.count()).select_from(entities.ChanStructureRevision)) == 3
        assert session.scalar(select(func.count()).select_from(entities.ChanObservedTransition)) == 3
        assert session.scalar(select(func.count()).select_from(entities.ChanResearchStreamHead)) == 1
        head = session.scalar(select(entities.ChanResearchStreamHead))
        assert head is not None
        first_row = session.scalar(
            select(entities.ChanResearchObservation)
            .where(entities.ChanResearchObservation.stream_id == head.stream_id)
            .order_by(entities.ChanResearchObservation.sequence_number)
            .limit(1)
        )
        assert first_row is not None and head.latest_sequence_number == 3

    with migrated_postgres_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE chan_research_stream_heads "
                "SET latest_sequence_number = latest_sequence_number, "
                "latest_observation_id = latest_observation_id WHERE stream_id = :stream_id"
            ),
            {"stream_id": head.stream_id},
        )

    with migrated_postgres_engine.connect() as connection:
        transaction = connection.begin()
        with pytest.raises(DBAPIError):
            connection.execute(
                text(
                    "UPDATE chan_research_stream_heads "
                    "SET latest_sequence_number = :sequence_number, latest_observation_id = :observation_id "
                    "WHERE stream_id = :stream_id"
                ),
                {
                    "sequence_number": first_row.sequence_number,
                    "observation_id": first_row.observation_id,
                    "stream_id": head.stream_id,
                },
            )
        transaction.rollback()

    for statement in (
        "UPDATE chan_research_observations SET stream_id = stream_id",
        "DELETE FROM chan_research_observations",
        "UPDATE chan_structure_revisions SET stream_id = stream_id",
        "DELETE FROM chan_structure_revisions",
        "UPDATE chan_observed_transitions SET stream_id = stream_id",
        "DELETE FROM chan_observed_transitions",
        "UPDATE chan_research_stream_heads SET stream_id = 'tampered'",
        "UPDATE chan_research_stream_heads SET config_id = 'tampered'",
        "UPDATE chan_research_stream_heads SET instrument = 'tampered'",
        "DELETE FROM chan_research_stream_heads",
    ):
        with migrated_postgres_engine.connect() as connection:
            transaction = connection.begin()
            with pytest.raises(DBAPIError):
                connection.execute(text(statement))
            transaction.rollback()


@pytest.mark.parametrize("failed_model_name", ["ChanStructureRevision", "ChanObservedTransition"])
def test_failed_later_publication_preserves_committed_head_and_evidence(migrated_engine, failed_model_name):
    entities = _module("app.models.entities")
    publisher_module = _module("app.services.chan_observation_service")
    stream_config = f"failure-case-{failed_model_name}"
    first = _observation(input_revision="input-r1", high=103.0, config_id=stream_config)
    second = _observation(input_revision="input-r2", high=104.0, config_id=stream_config)
    with Session(migrated_engine, expire_on_commit=False) as initial_session:
        with initial_session.begin():
            first_result = publisher_module.ChanObservationPublisher(initial_session).publish(first)

    def snapshot(session):
        head = session.scalar(
            select(entities.ChanResearchStreamHead).where(
                entities.ChanResearchStreamHead.stream_id == first_result.stream_id
            )
        )
        observations = list(
            session.scalars(
                select(entities.ChanResearchObservation)
                .where(entities.ChanResearchObservation.stream_id == first_result.stream_id)
                .order_by(entities.ChanResearchObservation.sequence_number)
            )
        )
        revisions = list(
            session.scalars(
                select(entities.ChanStructureRevision)
                .where(entities.ChanStructureRevision.stream_id == first_result.stream_id)
                .order_by(entities.ChanStructureRevision.revision_id)
            )
        )
        transitions = list(
            session.scalars(
                select(entities.ChanObservedTransition)
                .where(entities.ChanObservedTransition.stream_id == first_result.stream_id)
                .order_by(entities.ChanObservedTransition.observation_id, entities.ChanObservedTransition.structure_key)
            )
        )
        assert head is not None
        return (
            (head.stream_id, head.latest_sequence_number, head.latest_observation_id, head.config_id),
            tuple((row.observation_id, row.sequence_number, row.payload_hash) for row in observations),
            tuple((row.revision_id, row.structure_key, row.payload_hash) for row in revisions),
            tuple(
                (
                    row.observation_id,
                    row.structure_key,
                    row.status,
                    row.revision_id,
                    row.prior_revision_id,
                    row.reappearance,
                )
                for row in transitions
            ),
        )

    with Session(migrated_engine) as before_session:
        old_snapshot = snapshot(before_session)
    model = getattr(entities, failed_model_name)

    def reject_later_insert(mapper, connection, target):
        del mapper, connection, target
        raise RuntimeError(f"injected {failed_model_name} insert failure")

    from sqlalchemy import event

    event.listen(model, "before_insert", reject_later_insert)
    try:
        with Session(migrated_engine) as failure_session:
            with pytest.raises(RuntimeError, match="injected .* insert failure"):
                with failure_session.begin():
                    publisher_module.ChanObservationPublisher(failure_session).publish(second)
    finally:
        event.remove(model, "before_insert", reject_later_insert)

    with Session(migrated_engine) as after_session:
        assert snapshot(after_session) == old_snapshot
        assert after_session.get(entities.ChanResearchObservation, second.observation_id) is None
