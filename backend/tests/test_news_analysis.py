from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from app.analysis.contracts import (
    AnalysisEnvelope,
    AnalysisOutput,
    AnalysisProvider,
    AnalysisStatus,
    DataProvenance,
    VerifiedAnalysisInput,
)
from app.models import AnalysisRun, EventLog, Instrument, NewsItem, ProviderAudit
from app.providers.types import NewsRecord
from app.services.analysis_persistence_service import AnalysisPersistenceService
from app.services.dashboard_service import DashboardService
from app.services.llm_service import OpenAICompatibleClient
from app.services.news_service import NewsProviderRefreshError, NewsService
from app.services.signal_service import SignalService
from app.services.task_service import TaskService
from sqlalchemy import select, text


@pytest.fixture(scope="session", autouse=True)
def migrated_analysis_triggers(database) -> None:
    """Install only the migration-owned SQLite guards needed by persistence tests."""
    from app.db.session import get_engine

    with get_engine().begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TRIGGER IF NOT EXISTS trg_analysis_runs_append_only
            BEFORE UPDATE ON analysis_runs BEGIN
                SELECT RAISE(ABORT, 'analysis_runs are append-only');
            END
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TRIGGER IF NOT EXISTS trg_analysis_runs_no_delete
            BEFORE DELETE ON analysis_runs BEGIN
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
            BEFORE DELETE ON agent_review_candidates BEGIN
                SELECT RAISE(ABORT, 'review candidates are append-only');
            END
            """
        )


class FakeProvider:
    name = "fake-news-provider"

    def __init__(self, *records: NewsRecord) -> None:
        self.records = list(records)
        self.calls = 0

    def fetch_news(self, since_hours: int = 24) -> list[NewsRecord]:
        self.calls += 1
        return list(self.records)


class FakeAnalysisService:
    def __init__(self, envelope: AnalysisEnvelope, *, bind_input: bool = True) -> None:
        self.envelope = envelope
        self.bind_input = bind_input
        self.inputs = []
        self.close_calls = 0

    def analyze(self, input_data):
        self.inputs.append(input_data)
        return (
            self.envelope.model_copy(update={"input_hash": input_data.input_hash})
            if self.bind_input
            else self.envelope
        )

    def close(self) -> None:
        self.close_calls += 1


class TrackingPersistence:
    def __init__(self) -> None:
        self.calls = []

    def record(self, db, envelope, news_item_id=None, **kwargs):
        self.calls.append((envelope, news_item_id, kwargs))
        return AnalysisPersistenceService.record(db, envelope, news_item_id=news_item_id, **kwargs)


def _record(source_id: str = "n1") -> NewsRecord:
    return NewsRecord(
        source="a3b1-news",
        source_id=source_id,
        title="科技创新增长，行业景气改善",
        summary="摘要仅作为不可信新闻文本。",
        url="https://example.invalid/news/1",
        published_at=datetime.now(UTC),
    )


def _settings(**kwargs):
    from app.core.config import Settings

    return Settings(_env_file=None, **kwargs)


def _enabled_settings():
    return _settings(
        analysis_enabled=True,
        analysis_primary_provider=AnalysisProvider.CODEX_OPENAI_RESPONSES,
        analysis_primary_model="verified-model",
        analysis_primary_mode="responses",
        analysis_codex_enabled=True,
        openai_api_key="test-key-not-a-real-secret",
    )


def _completed_envelope(input_hash: str) -> AnalysisEnvelope:
    output = AnalysisOutput(
        facts=("model fact",),
        inferences=("model inference",),
        risk_flags=("model risk",),
        affected_themes=("model-only-theme",),
        evidence_ids=("model:evidence",),
        confidence_statement="仅作研究候选，不构成交易建议",
        provider=AnalysisProvider.CODEX_OPENAI_RESPONSES,
        model="verified-model",
        prompt_version="analysis-v1",
    )
    return AnalysisEnvelope(
        status=AnalysisStatus.COMPLETED,
        provider=AnalysisProvider.CODEX_OPENAI_RESPONSES,
        model="verified-model",
        latency_ms=2,
        input_hash=input_hash,
        prompt_version="analysis-v1",
        schema_version="analysis-v1",
        output=output,
        result_hash=output.result_hash,
    )


def _unavailable_envelope(input_hash: str, status=AnalysisStatus.ANALYSIS_UNAVAILABLE) -> AnalysisEnvelope:
    return AnalysisEnvelope(
        status=status,
        provider=AnalysisProvider.CODEX_OPENAI_RESPONSES,
        model="verified-model",
        latency_ms=2,
        input_hash=input_hash,
        prompt_version="analysis-v1",
        schema_version="analysis-v1",
        failure_class="httpx.ConnectError" if status is AnalysisStatus.ANALYSIS_UNAVAILABLE else "invalid_json",
    )


def test_disabled_analysis_keeps_heuristic_and_makes_no_analysis_calls(db_session) -> None:
    provider = FakeProvider(_record("disabled"))
    analysis = FakeAnalysisService(_unavailable_envelope("a" * 64))
    persistence = TrackingPersistence()

    result = NewsService(
        provider,
        _settings(analysis_enabled=False),
        analysis_service=analysis,
        persistence_service=persistence,
    ).refresh(db_session)

    row = db_session.scalar(select(NewsItem).where(NewsItem.source_id == "disabled"))
    assert row is not None
    assert row.analysis_source == "heuristic"
    assert row.analysis_status == "disabled"
    assert row.analysis_run_id is None
    assert analysis.inputs == []
    assert persistence.calls == []
    assert result["analysis_disabled"] == 1


def test_completed_model_analysis_is_persisted_but_cannot_replace_heuristic_fields(db_session) -> None:
    provider = FakeProvider(_record("completed"))
    analysis = FakeAnalysisService(_completed_envelope("a" * 64))
    persistence = TrackingPersistence()
    service = NewsService(
        provider,
        _enabled_settings(),
        analysis_service=analysis,
        persistence_service=persistence,
    )
    heuristic = service._heuristic_analysis(provider.records[0].title, provider.records[0].summary)

    result = service.refresh(db_session)
    row = db_session.scalar(select(NewsItem).where(NewsItem.source_id == "completed"))
    run = db_session.scalar(select(AnalysisRun).where(AnalysisRun.id == row.analysis_run_id))
    assert row is not None and run is not None
    assert row.analysis_status == "completed"
    assert row.analysis_source == "codex_openai_responses"
    assert row.impact_score == heuristic.impact_score
    assert row.impact_direction == heuristic.impact_direction
    assert row.affected_themes_json == heuristic.affected_themes
    assert row.facts_json == heuristic.facts
    assert json.loads(run.output_json)["facts"] == ["model fact"]
    assert json.loads(run.output_json)["affected_themes"] == ["model-only-theme"]
    assert result["analysis_completed"] == 1
    assert analysis.inputs[0].instrument is None
    assert analysis.inputs[0].news_title == provider.records[0].title
    assert analysis.close_calls == 0, "injected analysis service is caller-owned"


@pytest.mark.parametrize("status", [AnalysisStatus.ANALYSIS_UNAVAILABLE, AnalysisStatus.INVALID_RESPONSE])
def test_unavailable_or_invalid_model_analysis_is_linked_without_heuristic_masquerading(
    db_session, status
) -> None:
    source_id = f"{status.value}-news"
    provider = FakeProvider(_record(source_id))
    analysis = FakeAnalysisService(_unavailable_envelope("b" * 64, status))
    persistence = TrackingPersistence()
    service = NewsService(provider, _enabled_settings(), analysis_service=analysis, persistence_service=persistence)
    heuristic = service._heuristic_analysis(provider.records[0].title, provider.records[0].summary)

    result = service.refresh(db_session)
    row = db_session.scalar(select(NewsItem).where(NewsItem.source_id == source_id))
    assert row is not None
    assert row.analysis_run_id is not None
    assert row.analysis_status == status.value
    assert row.analysis_source == "codex_openai_responses"
    assert row.impact_score == heuristic.impact_score
    assert row.affected_themes_json == heuristic.affected_themes
    expected_counter = "analysis_unavailable" if status is AnalysisStatus.ANALYSIS_UNAVAILABLE else "analysis_invalid"
    assert result[expected_counter] == 1
    assert result.get("analysis_completed", 0) == 0
    run = db_session.get(AnalysisRun, row.analysis_run_id)
    assert run is not None and run.output_json is None
    payload = json.dumps(row.__dict__, ensure_ascii=False, default=str)
    assert "ConnectError" not in payload and "invalid_json" not in payload


def test_model_unrelated_theme_does_not_change_signal_theme_score(db_session) -> None:
    instrument = Instrument(
        ts_code="510999.SH",
        symbol="510999",
        name="测试科技 ETF",
        kind="ETF",
        exchange="SSE",
        theme_l1="科技",
        theme_l2="半导体",
        enabled=True,
    )
    db_session.add(instrument)
    db_session.flush()
    provider = FakeProvider(_record("signal-boundary"))
    analysis = FakeAnalysisService(_completed_envelope("c" * 64))
    NewsService(provider, _enabled_settings(), analysis_service=analysis).refresh(db_session)
    row = db_session.scalar(select(NewsItem).where(NewsItem.source_id == "signal-boundary"))
    assert row is not None
    deterministic_fields = (
        row.facts_json,
        row.inferences_json,
        row.risk_flags_json,
        row.affected_themes_json,
        row.impact_direction,
        row.impact_horizon,
        row.llm_model,
    )
    assert all("model-only-theme" not in (field or []) for field in deterministic_fields)
    now = datetime.now(UTC)
    signal_settings = _settings()
    recent_rows = db_session.scalars(
        select(NewsItem)
        .where(NewsItem.published_at >= now - timedelta(hours=72))
        .order_by(NewsItem.published_at.desc())
    ).all()
    themes = {value for value in (instrument.theme_l1, instrument.theme_l2) if value}
    expected_impacts = []
    expected_evidence = []
    for news_item in recent_rows:
        matched = any(
            any(theme in affected or affected in theme for affected in (news_item.affected_themes_json or []))
            for theme in themes
        )
        if not matched:
            continue
        published_at = news_item.published_at
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=signal_settings.timezone)
        age_hours = max(0.0, (now - published_at).total_seconds() / 3600)
        decay = max(0.2, 1 - age_hours / 96)
        expected_impacts.append(float(news_item.impact_score or 0) * decay)
        expected_evidence.append(news_item.title)
    expected_score = (
        round(max(0.0, min(100.0, 50 + 35 * sum(expected_impacts) / max(1, len(expected_impacts)))), 2)
        if expected_impacts
        else 50.0
    )
    score, evidence = SignalService(signal_settings)._news_theme_score(db_session, instrument, now)
    assert score == expected_score
    assert evidence == expected_evidence[:5]


def test_analyze_existing_does_not_call_provider_and_dashboard_separates_model_analysis(db_session) -> None:
    provider = FakeProvider(_record("existing"))
    analysis = FakeAnalysisService(_completed_envelope("d" * 64))
    persistence = TrackingPersistence()
    service = NewsService(provider, _enabled_settings(), analysis_service=analysis, persistence_service=persistence)
    service.refresh(db_session)
    provider.calls = 0
    analysis.inputs.clear()

    expected_rows = db_session.scalars(
        select(NewsItem).order_by(NewsItem.published_at.desc()).limit(10)
    ).all()
    expected_titles = [item.title for item in expected_rows]
    result = service.analyze_existing(db_session, limit=10, force=True)
    dashboard = DashboardService(_enabled_settings()).recent_news(db_session, limit=10)
    row = next(item for item in dashboard if item["source_id"] == "existing")
    assert provider.calls == 0
    assert len(analysis.inputs) == len(expected_rows)
    assert [item.news_title for item in analysis.inputs] == expected_titles
    assert result["provider_calls"] == 0
    assert result["updated"] == len(expected_rows)
    assert result["analysis_completed"] == len(expected_rows)
    existing_input = next(item for item in analysis.inputs if item.news_title == provider.records[0].title)
    assert existing_input.evidence_ids == (
        f"news:{provider.records[0].source}:{provider.records[0].source_id}",
    )
    assert row["analysis"]["status"] == "completed"
    assert row["analysis"]["provider"] == "codex_openai_responses"
    assert row["analysis"]["model"] == "verified-model"
    assert row["analysis"]["input_hash"] == existing_input.input_hash
    assert row["analysis"]["analysis_run_id"] is not None
    assert row["analysis"]["model_analysis"]["facts"] == ["model fact"]
    assert row["analysis"]["model_analysis"]["evidence_ids"] == ["model:evidence"]
    assert row["facts"] != row["analysis"]["model_analysis"]["facts"]


@pytest.mark.parametrize("status", [AnalysisStatus.COMPLETED, AnalysisStatus.ANALYSIS_UNAVAILABLE])
@pytest.mark.parametrize("field", ["input_hash", "provider", "model", "prompt_version", "schema_version"])
def test_mismatched_analysis_envelope_is_replaced_with_bound_invalid_response(
    db_session, status, field
) -> None:
    provider = FakeProvider(_record(f"mismatch-{status.value}-{field}"))
    settings = _enabled_settings()
    service = NewsService(provider, settings)
    data = service._analysis_input(provider.records[0])
    envelope = _completed_envelope(data.input_hash) if status is AnalysisStatus.COMPLETED else _unavailable_envelope(data.input_hash, status)
    bad_values = {
        "input_hash": "f" * 64,
        "provider": AnalysisProvider.ANTHROPIC_MESSAGES,
        "model": "wrong-model",
        "prompt_version": "wrong-prompt",
        "schema_version": "wrong-schema",
    }
    analysis = FakeAnalysisService(envelope.model_copy(update={field: bad_values[field]}), bind_input=False)
    persistence = TrackingPersistence()

    NewsService(provider, settings, analysis_service=analysis, persistence_service=persistence).refresh(db_session)

    row = db_session.scalar(select(NewsItem).where(NewsItem.source_id == provider.records[0].source_id))
    assert row is not None and row.analysis_run_id is not None
    run = db_session.get(AnalysisRun, row.analysis_run_id)
    assert run is not None
    assert row.analysis_status == AnalysisStatus.INVALID_RESPONSE.value
    assert row.analysis_source == AnalysisProvider.CODEX_OPENAI_RESPONSES.value
    assert run.status == AnalysisStatus.INVALID_RESPONSE.value
    assert run.provider == settings.analysis_primary_provider.value
    assert run.model == settings.analysis_primary_model
    assert run.input_hash == data.input_hash
    assert run.prompt_version == settings.analysis_prompt_version
    assert run.schema_version == settings.analysis_schema_version
    assert run.output_json is None
    assert "wrong" not in (run.failure_class or "")
    dashboard = DashboardService(settings).recent_news(db_session, limit=10)
    public = next(item["analysis"] for item in dashboard if item["source_id"] == provider.records[0].source_id)
    assert public["analysis_coherent"] is True
    assert public["status"] == AnalysisStatus.INVALID_RESPONSE.value
    assert public["model_analysis"] is None


def test_dashboard_rejects_raw_status_source_mismatch_and_orphan_link(db_session) -> None:
    settings = _enabled_settings()
    provider = FakeProvider(_record("dashboard-integrity"))
    analysis = FakeAnalysisService(_completed_envelope("a" * 64))
    NewsService(provider, settings, analysis_service=analysis).refresh(db_session)
    row = db_session.scalar(select(NewsItem).where(NewsItem.source_id == "dashboard-integrity"))
    assert row is not None
    db_session.execute(
        text(
            "UPDATE news_items SET analysis_source = 'wrong-provider' WHERE id = :id"
        ),
        {"id": row.id},
    )
    db_session.flush()
    mismatched = next(
        item["analysis"]
        for item in DashboardService(settings).recent_news(db_session, limit=10)
        if item["source_id"] == "dashboard-integrity"
    )
    assert mismatched["analysis_coherent"] is False
    assert mismatched["status"] == "invalid_provenance"
    assert mismatched["model_analysis"] is None
    db_session.rollback()

    from app.db.session import get_engine

    db_session.commit()
    raw = get_engine().raw_connection()
    try:
        raw.execute("PRAGMA foreign_keys=OFF")
        raw.execute(
            "INSERT INTO news_items "
            "(source, source_id, title, published_at, facts_json, inferences_json, risk_flags_json, "
            "affected_themes_json, impact_score, schema_version, quality_hash, analysis_run_id, analysis_source, analysis_status) "
            "VALUES ('raw', 'dashboard-orphan', 'orphan', CURRENT_TIMESTAMP, '[]', '[]', '[]', '[]', 0, 'news-v1', ?, 999999, 'codex_openai_responses', 'completed')",
            ("b" * 64,),
        )
        raw.commit()
    finally:
        raw.execute("PRAGMA foreign_keys=ON")
        raw.close()
    orphan = next(
        item["analysis"]
        for item in DashboardService(settings).recent_news(db_session, limit=1000)
        if item["source_id"] == "dashboard-orphan"
    )
    assert orphan["analysis_coherent"] is False
    assert orphan["status"] == "invalid_provenance"
    assert orphan["model_analysis"] is None


def test_analyze_existing_reuses_matching_completed_run_and_emits_event(db_session) -> None:
    provider = FakeProvider(_record("reuse-completed"))
    provider.records[0].published_at = datetime(2099, 1, 1, tzinfo=UTC)
    analysis = FakeAnalysisService(_completed_envelope("a" * 64))
    persistence = TrackingPersistence()
    service = NewsService(provider, _enabled_settings(), analysis_service=analysis, persistence_service=persistence)
    service.refresh(db_session)
    row = db_session.scalar(select(NewsItem).where(NewsItem.source_id == "reuse-completed"))
    assert row is not None
    original_run_id = row.analysis_run_id
    analysis.inputs.clear()
    persistence.calls.clear()

    result = service.analyze_existing(db_session, limit=1)

    assert result["analysis_reused"] == 1
    assert result["analysis_completed"] == 0
    assert analysis.inputs == []
    assert persistence.calls == []
    assert row.analysis_run_id == original_run_id
    event = db_session.scalar(
        select(EventLog).where(EventLog.event_type == "news.analysis.updated").order_by(EventLog.id.desc())
    )
    assert event is not None
    assert event.payload_json["run_id"] == result["run_id"]
    assert result["status"] == "succeeded"
    assert event.payload_json["analysis_reused"] >= 1


def test_analyze_existing_uses_supplied_run_id_and_never_calls_news_provider(db_session) -> None:
    provider = FakeProvider(_record("run-id-alignment"))
    analysis = FakeAnalysisService(_completed_envelope("a" * 64))
    service = NewsService(provider, _enabled_settings(), analysis_service=analysis)
    service.refresh(db_session, run_id="refresh-run")
    provider.calls = 0
    run_id = "task-run-aligned"

    result = service.analyze_existing(db_session, limit=1, force=True, run_id=run_id)
    event = db_session.scalar(
        select(EventLog).where(EventLog.event_type == "news.analysis.updated").order_by(EventLog.id.desc())
    )

    assert result["run_id"] == run_id
    assert result["status"] == "succeeded"
    assert event is not None
    assert event.payload_json["run_id"] == run_id
    assert provider.calls == 0


def test_task_service_passes_task_run_id_to_news_analysis(db_session) -> None:
    calls: list[dict[str, object]] = []

    class NewsStub:
        def analyze_existing(self, db, *, limit, force, run_id):
            calls.append({"db": db, "limit": limit, "force": force, "run_id": run_id})
            return {"run_id": run_id, "status": "succeeded", "provider_calls": 0}

    task_service = TaskService.__new__(TaskService)
    task_service.news = NewsStub()
    result = task_service._execute(
        db_session,
        "analyze_news",
        "task-run-id",
        limit=3,
        force=False,
    )

    assert result["run_id"] == "task-run-id"
    assert result["status"] == "succeeded"
    assert result["provider_calls"] == 0
    assert calls == [{"db": db_session, "limit": 3, "force": False, "run_id": "task-run-id"}]


def test_analyze_existing_force_always_creates_new_analysis_run(db_session) -> None:
    provider = FakeProvider(_record("reuse-force"))
    provider.records[0].published_at = datetime(2099, 1, 2, tzinfo=UTC)
    analysis = FakeAnalysisService(_completed_envelope("a" * 64))
    persistence = TrackingPersistence()
    service = NewsService(provider, _enabled_settings(), analysis_service=analysis, persistence_service=persistence)
    service.refresh(db_session)
    row = db_session.scalar(select(NewsItem).where(NewsItem.source_id == "reuse-force"))
    assert row is not None
    original_run_id = row.analysis_run_id
    analysis.inputs.clear()
    persistence.calls.clear()

    result = service.analyze_existing(db_session, limit=1, force=True)

    assert result["analysis_reused"] == 0
    assert result["analysis_completed"] == 1
    assert len(analysis.inputs) == 1
    assert len(persistence.calls) == 1
    assert row.analysis_run_id != original_run_id


def test_news_analysis_and_dashboard_limits_clamp_and_tie_order_by_id(db_session) -> None:
    published_at = datetime(2026, 1, 1, tzinfo=UTC)
    records = tuple(
        NewsRecord(
            source="tie-order",
            source_id=f"tie-{index}",
            title=f"tie {index}",
            summary="summary",
            published_at=published_at,
        )
        for index in range(3)
    )
    service = NewsService(FakeProvider(*records), _settings(analysis_enabled=False))
    service.refresh(db_session)

    assert service.analyze_existing(db_session, limit=0)["updated"] == 0
    result = service.analyze_existing(db_session, limit=10_000)
    rows = db_session.scalars(select(NewsItem).where(NewsItem.source == "tie-order")).all()
    expected_ids = [row.source_id for row in sorted(rows, key=lambda row: row.id, reverse=True)]
    assert [row.source_id for row in db_session.scalars(select(NewsItem).where(NewsItem.source == "tie-order").order_by(NewsItem.id.desc())).all()] == expected_ids
    dashboard = DashboardService(_settings()).recent_news(db_session, limit=10_000)
    assert [item["source_id"] for item in dashboard if item["source"] == "tie-order"] == expected_ids
    assert result["updated"] >= 3


def test_analysis_input_marks_explicit_mock_provenance_only(db_session) -> None:
    composite_named = FakeProvider(
        NewsRecord(source="mock-news:fixture", source_id="mock-1", title="mock", published_at=datetime.now(UTC))
    )
    composite_named.name = "composite"
    service = NewsService(composite_named, _enabled_settings())
    mock_input = service._analysis_input(composite_named.records[0])
    assert mock_input.is_mock is True
    assert mock_input.is_degraded is True

    real = _record("real-source")
    real = NewsRecord(**{**real.to_dict(), "source": "real-mock-news-site"})
    real_input = service._analysis_input(real)
    assert real_input.is_mock is False
    assert real_input.is_degraded is False


def test_refresh_provider_failure_audits_and_raises_sanitized_error_without_analysis(db_session) -> None:
    class FailingProvider(FakeProvider):
        name = "failing-news"

        def fetch_news(self, since_hours: int = 24) -> list[NewsRecord]:
            self.calls += 1
            raise RuntimeError("secret-url=https://private.invalid/token?key=secret")

    analysis = FakeAnalysisService(_completed_envelope("a" * 64))
    provider = FailingProvider()
    with pytest.raises(NewsProviderRefreshError) as raised:
        NewsService(provider, _enabled_settings(), analysis_service=analysis).refresh(db_session)
    assert str(raised.value) == "fetch_news failed: RuntimeError"
    assert "private.invalid" not in str(raised.value)
    assert analysis.inputs == []
    audit = db_session.scalar(select(ProviderAudit).where(ProviderAudit.operation == "fetch_news").order_by(ProviderAudit.id.desc()))
    assert audit is not None and audit.status == "failed"
    assert "private.invalid" not in (audit.reason or "")
    events = db_session.scalars(select(EventLog).where(EventLog.event_type == "news.updated")).all()
    assert all(event.payload_json.get("run_id") != audit.run_id for event in events)


def test_failed_analysis_has_failed_counter_not_invalid(db_session) -> None:
    provider = FakeProvider(_record("failed-counter"))
    analysis = FakeAnalysisService(_unavailable_envelope("a" * 64, AnalysisStatus.FAILED))
    result = NewsService(provider, _enabled_settings(), analysis_service=analysis).refresh(db_session)
    assert result["analysis_failed"] == 1
    assert result["analysis_invalid"] == 0


def test_llm_compatibility_facade_uses_verified_input_and_preserves_ownership(monkeypatch) -> None:
    input_data = VerifiedAnalysisInput(
        provenance=DataProvenance(source="test"), news_title="title", news_body="body"
    )
    disabled = OpenAICompatibleClient(_settings(analysis_enabled=False))
    unavailable = disabled.analyze_news(input_data)
    assert unavailable.status is AnalysisStatus.ANALYSIS_UNAVAILABLE
    assert unavailable.output is None
    disabled.close()

    class Injected:
        def __init__(self) -> None:
            self.inputs = []
            self.close_calls = 0

        def analyze(self, value):
            self.inputs.append(value)
            return unavailable

        def close(self):
            self.close_calls += 1

    injected = Injected()
    caller_owned = OpenAICompatibleClient(_enabled_settings(), service=injected)
    assert caller_owned.analyze_news(input_data) is unavailable
    caller_owned.close()
    assert injected.inputs == [input_data]
    assert injected.close_calls == 0

    owned = Injected()
    monkeypatch.setattr("app.services.llm_service.AnalysisService", lambda settings: owned)
    internally_owned = OpenAICompatibleClient(_enabled_settings())
    internally_owned.close()
    assert owned.close_calls == 1
