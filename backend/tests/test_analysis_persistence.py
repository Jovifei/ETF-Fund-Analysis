from __future__ import annotations

import hashlib
import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.analysis.contracts import AnalysisEnvelope, AnalysisOutput, AnalysisProvider, AnalysisStatus
from app.db.base import Base
from app.models import AgentReviewCandidate, AnalysisRun, Holding, NewsItem, RuntimeSetting, SignalSnapshot
from app.services.analysis_persistence_service import (
    AnalysisPersistenceError,
    AnalysisPersistenceService,
    AnalysisStorageNotMigrated,
    ensure_analysis_storage_ready,
)
from app.services.review_service import CandidateNotFoundError, ReviewService
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


@pytest.fixture(scope="session", autouse=True)
def migrated_analysis_storage(database) -> None:
    """Install migration-owned triggers for ordinary service unit tests only."""
    from app.db.session import get_engine

    with get_engine().begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TRIGGER IF NOT EXISTS trg_analysis_runs_append_only
            BEFORE UPDATE ON analysis_runs
            BEGIN
                SELECT RAISE(ABORT, 'analysis_runs are append-only');
            END
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TRIGGER IF NOT EXISTS trg_analysis_runs_no_delete
            BEFORE DELETE ON analysis_runs
            BEGIN
                SELECT RAISE(ABORT, 'analysis_runs are append-only');
            END
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TRIGGER IF NOT EXISTS trg_agent_review_candidates_immutable
            BEFORE UPDATE ON agent_review_candidates
            WHEN NEW.candidate_id IS NOT OLD.candidate_id
              OR NEW.runner IS NOT OLD.runner
              OR NEW.bundle_hash IS NOT OLD.bundle_hash
              OR NEW.memo_hash IS NOT OLD.memo_hash
              OR NEW.memo_json IS NOT OLD.memo_json
              OR NEW.created_at IS NOT OLD.created_at
            BEGIN
                SELECT RAISE(ABORT, 'review candidate identity and evidence are immutable');
            END
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TRIGGER IF NOT EXISTS trg_agent_review_candidates_no_delete
            BEFORE DELETE ON agent_review_candidates
            BEGIN
                SELECT RAISE(ABORT, 'review candidates are append-only');
            END
            """
        )


def _output() -> AnalysisOutput:
    return AnalysisOutput(
        facts=("行业事实",),
        inferences=("研究推断",),
        risk_flags=("风险需人工复核",),
        affected_themes=("科技",),
        impact_horizon="1w",
        evidence_ids=("news:1",),
        confidence_statement="仅作研究候选，不构成交易建议",
    )


def _envelope(status: AnalysisStatus = AnalysisStatus.COMPLETED) -> AnalysisEnvelope:
    output = _output() if status is AnalysisStatus.COMPLETED else None
    return AnalysisEnvelope(
        status=status,
        provider=AnalysisProvider.CODEX_OPENAI_RESPONSES,
        model="verified-model",
        latency_ms=12.5,
        input_hash="a" * 64,
        prompt_version="analysis-v1",
        schema_version="analysis-v1",
        output=output,
        result_hash=output.result_hash if output else None,
        failure_class=None if output else "TimeoutError",
    )


def test_completed_envelope_persists_only_validated_output(db_session) -> None:
    run = AnalysisPersistenceService.record(db_session, _envelope())
    db_session.flush()

    stored = db_session.get(AnalysisRun, run.id)
    assert stored is not None
    assert stored.provider == "codex_openai_responses"
    assert stored.model == "verified-model"
    assert stored.status == "completed"
    assert stored.latency_ms == 12.5
    assert stored.input_hash == "a" * 64
    assert stored.prompt_version == "analysis-v1"
    assert stored.schema_version == "analysis-v1"
    assert stored.result_hash == _output().result_hash
    assert isinstance(stored.output_json, str)
    payload = json.loads(stored.output_json)
    assert payload["facts"] == ["行业事实"]
    assert hashlib.sha256(stored.output_json.encode("utf-8")).hexdigest() == stored.result_hash
    assert "raw_exception" not in payload
    assert "bundle" not in payload
    assert "secret" not in repr(stored)


def test_analysis_unavailable_persists_sanitized_failure_and_null_output(db_session) -> None:
    run = AnalysisPersistenceService.record(db_session, _envelope(AnalysisStatus.ANALYSIS_UNAVAILABLE))
    db_session.flush()

    assert run.output_json is None
    assert run.result_hash is None
    assert run.failure_class == "TimeoutError"


@pytest.mark.parametrize("field", ["input_hash", "result_hash"])
def test_invalid_hashes_are_rejected_at_model_boundary(field: str) -> None:
    values = {
        "provider": "codex_openai_responses",
        "model": "model",
        "status": "analysis_unavailable",
        "latency_ms": 1,
        "input_hash": "a" * 64,
        "prompt_version": "v1",
        "schema_version": "v1",
        "failure_class": "TimeoutError",
    }
    values[field] = "not-a-hash"
    with pytest.raises((ValueError, ValidationError)):
        AnalysisRun(**values)


def test_record_rejects_invalid_hash_even_when_given_mapping(db_session) -> None:
    payload = _envelope().model_dump(mode="json")
    payload["input_hash"] = "x"
    with pytest.raises((ValueError, ValidationError)):
        AnalysisPersistenceService.record(db_session, payload)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"expected_input_hash": "b" * 64},
        {"expected_provider": "anthropic_messages"},
        {"expected_model": "other-model"},
        {"expected_prompt_version": "other-prompt"},
        {"expected_schema_version": "other-schema"},
    ],
)
def test_record_revalidates_expected_provenance_contract(db_session, kwargs) -> None:
    with pytest.raises(AnalysisPersistenceError, match="provenance"):
        AnalysisPersistenceService.record(db_session, _envelope(), **kwargs)


def test_sqlite_trigger_readiness_requires_expected_table_owner() -> None:
    engine = create_engine("sqlite://")
    try:
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TRIGGER trg_analysis_runs_append_only BEFORE UPDATE ON agent_review_candidates "
                "BEGIN SELECT RAISE(ABORT, 'wrong owner'); END"
            )
            for name, table in (
                ("trg_analysis_runs_no_delete", "analysis_runs"),
                ("trg_agent_review_candidates_immutable", "agent_review_candidates"),
                ("trg_agent_review_candidates_no_delete", "agent_review_candidates"),
            ):
                connection.exec_driver_sql(
                    f"CREATE TRIGGER {name} BEFORE UPDATE ON {table} "
                    "BEGIN SELECT 1; END"
                )
        with Session(engine) as session:
            with pytest.raises(AnalysisStorageNotMigrated):
                ensure_analysis_storage_ready(session)
    finally:
        engine.dispose()


def test_sqlite_foreign_keys_are_enabled_and_reject_orphan_news_link(db_session) -> None:
    assert db_session.scalar(text("PRAGMA foreign_keys")) == 1
    item = NewsItem(
        source="raw-test",
        source_id="orphan-news",
        title="raw test",
        published_at=datetime.now(UTC),
        facts_json=[],
        inferences_json=[],
        risk_flags_json=[],
        affected_themes_json=[],
        quality_hash="a" * 64,
        analysis_run_id=987654321,
        analysis_source="codex_openai_responses",
        analysis_status="completed",
    )
    db_session.add(item)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_news_provenance_link_fields_exist_without_news_service_integration(db_session) -> None:
    from app.models import NewsItem

    assert not hasattr(AnalysisRun, "news_item_id")
    assert not AnalysisRun.__table__.foreign_keys
    assert hasattr(NewsItem, "analysis_run_id")
    assert hasattr(NewsItem, "analysis_source")
    assert hasattr(NewsItem, "analysis_status")


def test_enqueue_allowlists_runners_and_stores_stable_hashes_without_cli(monkeypatch, db_session) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("review persistence must not invoke a subprocess")

    monkeypatch.setattr("subprocess.run", fail_if_called)
    bundle = {"news_id": 7, "text": "untrusted"}
    memo = {"summary": "validated", "evidence_ids": ["news:1"], "risk_flags": [], "limitations": []}
    candidate = ReviewService.enqueue_candidate(
        db_session,
        runner="codex_review_runner",
        bundle=bundle,
        memo=memo,
    )
    db_session.flush()
    assert candidate.candidate_id
    assert len(candidate.bundle_hash) == 64
    assert len(candidate.memo_hash) == 64
    assert candidate.review_status == "pending"
    assert isinstance(candidate.memo_json, str)
    assert json.loads(candidate.memo_json) == memo
    assert db_session.scalar(select(AgentReviewCandidate).where(AgentReviewCandidate.id == candidate.id))

    with pytest.raises(ValueError):
        ReviewService.enqueue_candidate(
            db_session,
            runner="shell_runner",
            bundle=bundle,
            memo=memo,
        )


def test_review_memo_is_allowlisted_bounded_and_rejects_sensitive_content(db_session) -> None:
    valid = {"summary": "validated", "evidence_ids": ["news:1"], "risk_flags": [], "limitations": []}
    candidate = ReviewService.enqueue_candidate(
        db_session, runner="codex_review_runner", bundle={"news_id": 7}, memo=valid
    )
    assert json.loads(candidate.memo_json) == valid
    for invalid in (
        {"summary": "x", "bundle": "raw"},
        {"summary": "https://example.invalid"},
        {"summary": "Bearer abc"},
        {"summary": "password=secret"},
        {"summary": "C:\\private\\bundle.json"},
        {"summary": "Traceback (most recent call last):"},
        {"summary": "powershell -Command Get-ChildItem"},
    ):
        with pytest.raises(ValueError):
            ReviewService.enqueue_candidate(
                db_session, runner="codex_review_runner", bundle={"news_id": 7}, memo=invalid
            )


def test_canonical_json_rejects_special_float_constants_and_requires_object() -> None:
    from app.utils.canonical_json import canonical_dumps, canonical_loads

    with pytest.raises(ValueError):
        canonical_loads('{"value":NaN}')
    with pytest.raises(ValueError):
        canonical_dumps({"value": float("inf")})
    with pytest.raises(ValueError):
        canonical_loads("[1,2]", object_only=True)


def test_review_transition_is_atomic_across_two_file_sqlite_sessions(db_session) -> None:
    from app.db.session import SessionLocal

    candidate = ReviewService.enqueue_candidate(
        db_session,
        runner="codex_review_runner",
        bundle={"id": 11},
        memo={"summary": "race", "evidence_ids": [], "risk_flags": [], "limitations": []},
    )
    db_session.commit()
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def transition(target: str) -> None:
        session = SessionLocal()
        try:
            barrier.wait(timeout=5)
            try:
                getattr(ReviewService, target)(session, candidate.candidate_id, note=target)
                session.commit()
                outcomes.append(target)
            except ValueError:
                session.rollback()
                outcomes.append("opposite_rejected")
        finally:
            session.close()

    threads = [threading.Thread(target=transition, args=(name,)) for name in ("accept", "reject")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert not any(thread.is_alive() for thread in threads)
    assert sorted(outcomes).count("opposite_rejected") == 1
    assert sorted(outcomes).count("accept") + sorted(outcomes).count("reject") == 1


def test_raw_bulk_corruption_is_rejected_by_append_only_trigger(db_session) -> None:
    run = AnalysisPersistenceService.record(db_session, _envelope())
    db_session.flush()
    db_session.commit()
    with pytest.raises(IntegrityError, match="append-only"):
        db_session.execute(
            text("UPDATE analysis_runs SET output_json = :payload WHERE id = :id"),
            {"payload": '{"facts":["tampered"]}', "id": run.id},
        )
    db_session.rollback()


def test_db_status_and_timestamp_coherence_checks_reject_raw_invalid_rows(db_session) -> None:
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO analysis_runs "
                "(provider, model, status, latency_ms, input_hash, prompt_version, schema_version, result_hash, output_json, failure_class) "
                "VALUES ('codex_openai_responses', 'm', 'completed', 1, :h, 'p', 's', NULL, NULL, NULL)"
            ),
            {"h": "a" * 64},
        )
    db_session.rollback()
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO agent_review_candidates "
                "(candidate_id, runner, bundle_hash, memo_hash, memo_json, review_status, accepted_at, rejected_at) "
                "VALUES ('raw-coherence', 'codex_review_runner', :b, :m, :j, 'accepted', NULL, NULL)"
            ),
            {"b": "a" * 64, "m": "b" * 64, "j": '{"summary":"ok"}'},
        )


def test_candidate_terminal_transitions_are_idempotent_and_opposites_rejected(db_session) -> None:
    candidate = ReviewService.enqueue_candidate(
        db_session,
        runner="claude_code_review_runner",
        bundle={"bundle": "opaque"},
        memo={"summary": "bounded", "evidence_ids": [], "risk_flags": [], "limitations": []},
    )
    db_session.flush()
    accepted = ReviewService.accept(db_session, candidate.candidate_id, note="approved")
    accepted_at = accepted.accepted_at
    assert accepted.review_status == "accepted"
    assert accepted.review_note == "approved"
    assert accepted_at is not None
    assert ReviewService.accept(db_session, candidate.candidate_id, note="ignored").accepted_at == accepted_at
    with pytest.raises(ValueError):
        ReviewService.reject(db_session, candidate.candidate_id, note="opposite")
    with pytest.raises(CandidateNotFoundError):
        ReviewService.get(db_session, "missing-candidate")


def test_review_note_uses_two_thousand_character_bound(db_session) -> None:
    candidate = ReviewService.enqueue_candidate(
        db_session,
        runner="codex_review_runner",
        bundle={"id": 90},
        memo={"summary": "bounded", "evidence_ids": [], "risk_flags": [], "limitations": []},
    )
    with pytest.raises(ValueError, match="review_note"):
        ReviewService.accept(db_session, candidate.candidate_id, note="n" * 2001)
    accepted = ReviewService.accept(db_session, candidate.candidate_id, note="n" * 2000)
    assert len(accepted.review_note or "") == 2000


def test_rejected_candidate_has_timestamp_and_no_domain_side_effects(db_session) -> None:
    before_counts = {
        model: db_session.scalar(select(func.count()).select_from(model))
        for model in (AnalysisRun, Holding, SignalSnapshot, RuntimeSetting)
    }
    candidate = ReviewService.enqueue_candidate(
        db_session,
        runner="codex_review_runner",
        bundle={"id": 1},
        memo={"summary": "hold", "evidence_ids": [], "risk_flags": [], "limitations": []},
    )
    db_session.flush()
    rejected = ReviewService.reject(db_session, candidate.candidate_id, note="insufficient evidence")
    assert rejected.review_status == "rejected"
    assert rejected.rejected_at is not None
    assert rejected.accepted_at is None
    after_counts = {
        model: db_session.scalar(select(func.count()).select_from(model))
        for model in (AnalysisRun, Holding, SignalSnapshot, RuntimeSetting)
    }
    assert after_counts == before_counts
    assert not hasattr(ReviewService, "write_holdings")
    assert not hasattr(ReviewService, "write_signals")
    assert not hasattr(ReviewService, "write_settings")


def test_hash_arguments_must_be_strict_64_hex(db_session) -> None:
    with pytest.raises(ValueError):
        ReviewService.enqueue_candidate(
            db_session,
            runner="codex_review_runner",
            bundle_hash="a" * 63,
            memo_hash="b" * 64,
            memo={"summary": "ok", "evidence_ids": [], "risk_flags": [], "limitations": []},
        )
    with pytest.raises(ValueError):
        ReviewService.enqueue_candidate(
            db_session,
            runner="codex_review_runner",
            bundle_hash="g" * 64,
            memo_hash="b" * 64,
            memo={"summary": "ok", "evidence_ids": [], "risk_flags": [], "limitations": []},
        )


def test_persisted_payloads_are_immutable_strings_and_updates_are_rejected(db_session) -> None:
    run = AnalysisPersistenceService.record(db_session, _envelope())
    db_session.flush()
    assert isinstance(run.output_json, str)
    with pytest.raises(ValueError):
        run.input_hash = "b" * 64
        db_session.flush()
    db_session.rollback()


def test_raw_sql_cannot_persist_overlong_memo_or_review_note(db_session) -> None:
    candidate = ReviewService.enqueue_candidate(
        db_session,
        runner="codex_review_runner",
        bundle={"id": 91},
        memo={"summary": "bounded", "evidence_ids": [], "risk_flags": [], "limitations": []},
    )
    db_session.flush()
    db_session.commit()
    overlong_memo = json.dumps(
        {"summary": "ok", "evidence_ids": ["e" * 512] * 128},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert len(overlong_memo) > 12000
    with pytest.raises(IntegrityError):
        db_session.execute(
            text("UPDATE agent_review_candidates SET memo_json = :memo WHERE id = :id"),
            {"memo": overlong_memo, "id": candidate.id},
        )
    db_session.rollback()
    with pytest.raises(IntegrityError):
        db_session.execute(
            text("UPDATE agent_review_candidates SET review_note = :note WHERE id = :id"),
            {"note": "n" * 2001, "id": candidate.id},
        )
    db_session.rollback()


def test_review_integrity_rejects_raw_malformed_memo_update(db_session) -> None:
    candidate = ReviewService.enqueue_candidate(
        db_session,
        runner="codex_review_runner",
        bundle={"id": 92},
        memo={"summary": "bounded", "evidence_ids": [], "risk_flags": [], "limitations": []},
    )
    db_session.flush()
    db_session.commit()
    with pytest.raises(IntegrityError, match="immutable"):
        db_session.execute(
            text("UPDATE agent_review_candidates SET memo_json = :memo WHERE id = :id"),
            {"memo": '{"summary":"ok","unexpected":true}', "id": candidate.id},
        )
    db_session.rollback()

    run = AnalysisPersistenceService.record(db_session, _envelope())
    db_session.flush()
    with pytest.raises(ValueError):
        run.output_json = "{}"
        db_session.flush()
    db_session.rollback()

    candidate = ReviewService.enqueue_candidate(
        db_session,
        runner="codex_review_runner",
        bundle={"id": 2},
        memo={"summary": "bounded", "evidence_ids": [], "risk_flags": [], "limitations": []},
    )
    db_session.flush()
    assert isinstance(candidate.memo_json, str)
    candidate = db_session.get(AgentReviewCandidate, candidate.id)
    assert candidate is not None
    with pytest.raises(ValueError):
        candidate.bundle_hash = "c" * 64
        db_session.flush()
    db_session.rollback()


def test_migration_uses_single_fk_and_no_forced_news_table_recreation() -> None:
    migration = Path(__file__).parents[1] / "alembic" / "versions" / "9f1c2b3a4d5e_multi_model_analysis.py"
    source = migration.read_text(encoding="utf-8")
    assert 'sa.ForeignKeyConstraint(["news_item_id"]' not in source
    assert 'recreate="always"' not in source
    assert "fk_news_items_analysis_run_id" in source
    assert "NOT GLOB '*[^0-9A-Fa-f]*'" in source
    assert 'dialect == "postgresql"' in source
    assert "~ '^[0-9A-Fa-f]" in source
    assert "trg_analysis_runs_append_only" in source
    assert "trg_agent_review_candidates_immutable" in source
    assert "sqlite" in source and "postgresql" in source


def test_sqlite_hash_checks_reject_non_hex_raw_sql_and_accept_hex(db_session) -> None:
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO analysis_runs "
                "(provider, model, status, latency_ms, input_hash, prompt_version, schema_version, failure_class) "
                "VALUES ('codex_openai_responses', 'm', 'analysis_unavailable', 1, :h, 'p', 's', 'TimeoutError')"
            ),
            {"h": "z" * 64},
        )
        db_session.flush()
    db_session.rollback()
    db_session.execute(
        text(
            "INSERT INTO analysis_runs "
            "(provider, model, status, latency_ms, input_hash, prompt_version, schema_version, failure_class) "
            "VALUES ('codex_openai_responses', 'm', 'analysis_unavailable', 1, :h, 'p', 's', 'TimeoutError')"
        ),
        {"h": "aB" * 32},
    )
    db_session.flush()
    db_session.rollback()
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO agent_review_candidates "
                "(candidate_id, runner, bundle_hash, memo_hash, memo_json, review_status) "
                "VALUES ('raw-invalid', 'codex_review_runner', :b, :m, :j, 'pending')"
            ),
            {"b": "z" * 64, "m": "a" * 64, "j": '{"ok":true}'},
        )
    db_session.rollback()
    db_session.execute(
        text(
            "INSERT INTO agent_review_candidates "
            "(candidate_id, runner, bundle_hash, memo_hash, memo_json, review_status) "
            "VALUES ('raw-valid', 'codex_review_runner', :b, :m, :j, 'pending')"
        ),
        {"b": "aB" * 32, "m": "cD" * 32, "j": '{"ok":true}'},
    )
    db_session.flush()
    db_session.rollback()


def test_entities_require_canonical_object_json_and_hash_binding(db_session) -> None:
    output = _output().model_dump(mode="json")
    canonical = json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    values = {
        "provider": "codex_openai_responses",
        "model": "verified-model",
        "status": "completed",
        "latency_ms": 1,
        "input_hash": "a" * 64,
        "prompt_version": "p",
        "schema_version": "s",
        "result_hash": hashlib.sha256(canonical.encode()).hexdigest(),
        "output_json": canonical,
    }
    valid = AnalysisRun(**values)
    db_session.add(valid)
    db_session.flush()
    db_session.rollback()
    for bad_json in ("not-json", json.dumps(output, ensure_ascii=False), json.dumps([output])):
        with pytest.raises(ValueError):
            AnalysisRun(**{**values, "output_json": bad_json})
    with pytest.raises(ValueError):
        db_session.add(AnalysisRun(**{**values, "result_hash": "b" * 64}))
        db_session.flush()
    db_session.rollback()

    memo = {"summary": "ok"}
    memo_text = json.dumps(memo, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    candidate = AgentReviewCandidate(
        candidate_id="candidate-direct-1",
        runner="codex_review_runner",
        bundle_hash="c" * 64,
        memo_hash=hashlib.sha256(memo_text.encode()).hexdigest(),
        memo_json=memo_text,
        review_status="pending",
    )
    db_session.add(candidate)
    db_session.flush()
    db_session.rollback()
    mismatched = AgentReviewCandidate(
            candidate_id="candidate-direct-2",
            runner="codex_review_runner",
            bundle_hash="c" * 64,
            memo_hash="d" * 64,
            memo_json=memo_text,
            review_status="pending",
        )
    with pytest.raises(ValueError):
        db_session.add(mismatched)
        db_session.flush()
    db_session.rollback()


def test_auto_create_only_storage_fails_closed_before_any_rows_are_written() -> None:
    engine = create_engine("sqlite://")
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            with pytest.raises(AnalysisStorageNotMigrated):
                AnalysisPersistenceService.record(session, _envelope())
            assert session.scalar(select(func.count()).select_from(AnalysisRun)) == 0
            with pytest.raises(AnalysisStorageNotMigrated):
                ReviewService.enqueue_candidate(
                    session,
                    runner="codex_review_runner",
                    bundle={"id": "auto-create"},
                    memo={"summary": "blocked", "evidence_ids": [], "risk_flags": [], "limitations": []},
                )
            assert session.scalar(select(func.count()).select_from(AgentReviewCandidate)) == 0
    finally:
        engine.dispose()


def test_unknown_storage_dialect_fails_closed(db_session, monkeypatch) -> None:
    monkeypatch.setattr(
        db_session,
        "get_bind",
        lambda: SimpleNamespace(dialect=SimpleNamespace(name="unknown")),
    )
    with pytest.raises(AnalysisStorageNotMigrated):
        AnalysisPersistenceService.record(db_session, _envelope())


def test_migration_defines_append_only_delete_triggers_and_postgres_cleanup() -> None:
    migration = Path(__file__).parents[1] / "alembic" / "versions" / "9f1c2b3a4d5e_multi_model_analysis.py"
    source = migration.read_text(encoding="utf-8")
    assert "trg_analysis_runs_no_delete" in source
    assert "trg_agent_review_candidates_no_delete" in source
    assert "BEFORE DELETE ON analysis_runs" in source
    assert "BEFORE DELETE ON agent_review_candidates" in source
    assert "DROP TRIGGER IF EXISTS trg_analysis_runs_no_delete ON analysis_runs" in source
    assert "DROP TRIGGER IF EXISTS trg_agent_review_candidates_no_delete ON agent_review_candidates" in source
    assert "CREATE OR REPLACE FUNCTION reject_analysis_runs_delete()" in source
    assert "CREATE OR REPLACE FUNCTION reject_agent_review_candidate_delete()" in source


def test_raw_delete_is_rejected_by_migrated_sqlite_triggers_and_rows_remain(db_session) -> None:
    run = AnalysisPersistenceService.record(db_session, _envelope())
    candidate = ReviewService.enqueue_candidate(
        db_session,
        runner="codex_review_runner",
        bundle={"id": "delete-probe"},
        memo={"summary": "delete probe", "evidence_ids": [], "risk_flags": [], "limitations": []},
    )
    db_session.flush()
    db_session.commit()
    with pytest.raises(IntegrityError, match="append-only"):
        db_session.execute(text("DELETE FROM analysis_runs WHERE id = :id"), {"id": run.id})
    db_session.rollback()
    with pytest.raises(IntegrityError, match="append-only"):
        db_session.execute(
            text("DELETE FROM agent_review_candidates WHERE id = :id"), {"id": candidate.id}
        )
    db_session.rollback()
    assert db_session.scalar(select(func.count()).select_from(AnalysisRun)) >= 1
    assert db_session.scalar(select(func.count()).select_from(AgentReviewCandidate)) >= 1
