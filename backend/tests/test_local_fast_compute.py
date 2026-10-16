"""A fast publication may reuse only the exact settled computation inputs."""
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import Base
from app.models import DailyBar, ForecastSnapshot, IndicatorSnapshot, Instrument, TaskRun
from app.utils.hashing import stable_hash
from app.workspace import local_compute as local

SHA = "a" * 40
DAY = date(2026, 10, 15)


@pytest.fixture
def baseline(tmp_path, monkeypatch):
    path = tmp_path / "research.sqlite3"
    settings = Settings(_env_file=None, market_provider="public_composite", database_url=f"sqlite:///{path}")
    now = datetime(2026, 10, 16, 14, 30, tzinfo=settings.timezone)
    monkeypatch.setattr("app.services.settlement.settled_session", lambda *a, **k: DAY)
    monkeypatch.setattr("app.services.trading_calendar_service.TradingCalendarService.decision",
                        lambda *a: SimpleNamespace(verified=True, is_trade_day=True))
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)
    cfg = settings.load_strategy()
    cfg["forecast"]["min_history"] = 30
    monkeypatch.setattr(Settings, "load_strategy", lambda self: cfg)
    with Session(engine) as db, db.begin():
        instruments = [Instrument(ts_code=f"{510000+i}.SH", symbol=str(510000+i), name="synthetic", enabled=True)
                       for i in range(3)]
        db.add_all(instruments); db.flush()
        codes = [item.ts_code for item in instruments[:2]]
        from app.services.execution_scope import execution_scope
        scope = execution_scope(instruments, codes)
        for item in instruments:
            for offset in range(35):
                db.add(DailyBar(instrument_id=item.id, trade_date=DAY-timedelta(days=34-offset),
                               open=1, high=1, low=1, close=1, volume=10, amount=10,
                               adjust="qfq", source="akshare:em:v101", quality_hash="b"*64))
        for item in instruments[:2]:
            db.flush()
            from app.utils.input_lineage import history_digest, calculation_digest
            hashes = {i.id: history_digest(db.scalars(select(DailyBar).where(DailyBar.instrument_id == i.id)
                      .order_by(DailyBar.trade_date)).all()) for i in instruments}
            def input_hash(kind):
                return stable_hash({"panel": calculation_digest(hashes, cfg, f"{kind}-panel-v2"),
                                    "instrument_id": item.id, "local": hashes[item.id]})
            db.add(IndicatorSnapshot(instrument_id=item.id, as_of_date=DAY, version=cfg["indicator_version"],
                values_json={}, technical_score=50, risk_score=50, trend_label="synthetic", data_quality=100,
                input_hash=input_hash("indicator"), feature_schema_version=cfg["feature_schema_version"],
                config_hash=stable_hash(cfg), git_commit_sha=SHA, generated_at=now-timedelta(minutes=10)))
            for horizon in cfg["forecast"]["horizons"]:
                db.add(ForecastSnapshot(instrument_id=item.id, as_of_date=DAY, horizon=int(horizon),
                    model_version=cfg["forecast_version"], input_hash=input_hash("forecast"),
                    feature_schema_version=cfg["feature_schema_version"], config_hash=stable_hash(cfg),
                    git_commit_sha=SHA, diagnostics_json={}, generated_at=now-timedelta(minutes=9)))
        for name in ("refresh_bars", "refresh_indicators", "refresh_forecasts"):
            db.add(TaskRun(run_id=name, task_name=name, status="succeeded", started_at=now-timedelta(minutes=20),
                finished_at=now-timedelta(minutes=8), result_json={"status":"succeeded", "coverage_complete":True,
                "target_trade_date":DAY.isoformat(), "execution_scope":scope,
                "coverage": [{"ts_code": code, "complete": True, "received_through": DAY.isoformat()} for code in codes]}))
    yield settings, codes, now, engine
    engine.dispose()


def test_base_is_bound_to_actual_all_background_inputs(baseline):
    settings, codes, now, engine = baseline
    base = local.create_base_manifest(settings, codes, code_sha=SHA, now=now)
    assert base["background_count"] == 3 and base["target_codes"] == sorted(codes)
    assert local.validate_base_manifest(settings, codes, base, code_sha=SHA, now=now) == base
    with Session(engine) as db, db.begin():
        db.scalar(select(DailyBar).where(DailyBar.instrument_id == 3)).close = 1.01
    with pytest.raises(ValueError, match="base"):
        local.validate_base_manifest(settings, codes, base, code_sha=SHA, now=now)


def test_base_creation_rejects_history_changed_since_actual_calculation(baseline):
    settings, codes, now, engine = baseline
    with Session(engine) as db, db.begin():
        db.scalar(select(DailyBar).where(DailyBar.instrument_id == 3)).amount = 11
    with pytest.raises(ValueError, match="base snapshot"):
        local.create_base_manifest(settings, codes, code_sha=SHA, now=now)


@pytest.mark.parametrize("case", ["scope", "code", "session", "snapshot", "new_failure", "forged_hash",
                                  "quality", "background", "forecast_missing", "database_clone"])
def test_base_fails_closed_on_identity_or_quality_change(baseline, monkeypatch, case):
    settings, codes, now, engine = baseline
    base = local.create_base_manifest(settings, codes, code_sha=SHA, now=now)
    check_codes, check_sha = codes, SHA
    if case == "scope": check_codes = codes[:1]
    if case == "code": check_sha = "e"*40
    if case == "session":
        monkeypatch.setattr("app.services.settlement.settled_session", lambda *a, **k: DAY+timedelta(days=1))
    if case == "snapshot":
        with Session(engine) as db, db.begin():
            db.scalar(select(IndicatorSnapshot)).config_hash = "wrong"
    if case == "new_failure":
        with Session(engine) as db, db.begin():
            db.add(TaskRun(run_id="failed", task_name="refresh_bars", status="partial", started_at=now,
                           finished_at=now, result_json={}))
    if case == "forged_hash": base["input_hash"] = "0"*64
    if case == "quality":
        with Session(engine) as db, db.begin():
            db.scalar(select(DailyBar)).source = "unknown_endpoint"
    if case == "background":
        with Session(engine) as db, db.begin():
            db.scalar(select(Instrument).where(Instrument.id == 3)).enabled = False
    if case == "forecast_missing":
        with Session(engine) as db, db.begin():
            db.delete(db.scalar(select(ForecastSnapshot)))
    if case == "database_clone":
        import sqlite3
        clone = engine.url.database + ".clone"
        with sqlite3.connect(engine.url.database) as source, sqlite3.connect(clone) as destination:
            source.backup(destination)
        settings = settings.model_copy(update={"database_url": f"sqlite:///{clone}"})
    with pytest.raises(ValueError, match="base"):
        local.validate_base_manifest(settings, check_codes, base, code_sha=check_sha, now=now)


def test_fast_rejects_invalid_base_before_any_provider_call(baseline, monkeypatch):
    settings, codes, now, _ = baseline
    def forbidden(*a, **k): raise AssertionError("provider instantiated before base validation")
    monkeypatch.setattr("app.services.task_service.TaskService", forbidden)
    with pytest.raises(ValueError, match="base"):
        local.compute_local_fast(settings, codes, base_manifest={}, code_sha=SHA,
                                 private_research=True, now=now)


def fake_fast_tasks(monkeypatch, now, *, mode=None):
    from app.models import QuoteSnapshot, DecisionBoardProvisionalInput
    calls = []
    class Tasks:
        def __init__(self, settings, **kwargs):
            assert kwargs["execution_policy"].resolve_runtime_provider is False
        def close(self): pass
        def run(self, db, task, **kwargs):
            calls.append((task, kwargs))
            if task == "refresh_quotes":
                for item in db.scalars(select(Instrument).where(Instrument.ts_code.in_(kwargs["codes"]))):
                    stamp = now-timedelta(minutes=9 if mode == "stale" else 0)
                    db.add(QuoteSnapshot(instrument_id=item.id, quote_time=stamp, fetched_at=now,
                        timestamp_verified=True, price=1.1, open=1, high=1.2, low=0.9, volume=10,
                        amount=11, pct_change=10, source="sina:hq_sinajs:v1", is_realtime=mode != "nonrealtime",
                        quality_hash="e"*64))
                    if mode == "conflict":
                        db.add(DecisionBoardProvisionalInput(instrument_id=item.id, observed_at=stamp,
                            source="sina:hq_sinajs:v1", timestamp_verified=True, last_price=9))
                db.flush()
            if task == "refresh_decision_board":
                assert len(db.scalars(select(DecisionBoardProvisionalInput)).all()) == 2
            return {"status": "partial" if mode == "partial" else "succeeded"}
    monkeypatch.setattr("app.services.task_service.TaskService", Tasks)
    return calls


def test_fast_only_recomputes_quote_dependent_stages_and_revalidates_export(baseline, monkeypatch):
    settings, codes, now, engine = baseline
    base = local.create_base_manifest(settings, codes, code_sha=SHA, now=now)
    calls = fake_fast_tasks(monkeypatch, now)
    observed = []
    def committed(task, result, run_id):
        if result is None:
            return
        assert run_id and result["status"] == "succeeded"
        observed.append(task)
        if task == "refresh_quotes":
            from app.models import DecisionBoardProvisionalInput
            with Session(engine) as db:
                assert len(db.scalars(select(DecisionBoardProvisionalInput)).all()) == 2
    results = local.compute_local_fast(settings, codes, base_manifest=base, code_sha=SHA,
                                       private_research=True, now=now, on_task=committed)
    assert [task for task, _ in calls] == observed == ["refresh_quotes", "refresh_signals", "refresh_decision_board"]
    assert all(kwargs["codes"] == codes for _, kwargs in calls)
    assert local.validate_base_manifest(settings, codes, base, code_sha=SHA, now=now) == base
    local.validate_fast_result(settings, codes, results, now=now)
    with pytest.raises(ValueError, match="stale"):
        local.validate_fast_result(settings, codes, results, now=now+timedelta(minutes=8, seconds=1))


def test_export_revalidation_binds_content_not_only_quote_ids(baseline, monkeypatch):
    from app.models import QuoteSnapshot
    settings, codes, now, engine = baseline
    base = local.create_base_manifest(settings, codes, code_sha=SHA, now=now)
    fake_fast_tasks(monkeypatch, now)
    results = local.compute_local_fast(settings, codes, base_manifest=base, code_sha=SHA,
                                       private_research=True, now=now)
    with Session(engine) as db, db.begin():
        db.scalar(select(QuoteSnapshot)).price = 1.15
    with pytest.raises(ValueError, match="content changed"):
        local.validate_fast_result(settings, codes, results, now=now)


@pytest.mark.parametrize("mode", ["stale", "nonrealtime", "conflict", "partial"])
def test_fast_never_promotes_bad_or_partial_quotes(baseline, monkeypatch, mode):
    settings, codes, now, _ = baseline
    base = local.create_base_manifest(settings, codes, code_sha=SHA, now=now)
    calls = fake_fast_tasks(monkeypatch, now, mode=mode)
    if mode == "partial":
        result = local.compute_local_fast(settings, codes, base_manifest=base, code_sha=SHA,
                                          private_research=True, now=now)
        assert len(result) == 1 and result[0]["status"] == "partial"
    else:
        with pytest.raises(ValueError, match="fast"):
            local.compute_local_fast(settings, codes, base_manifest=base, code_sha=SHA,
                                     private_research=True, now=now)
    assert [task for task, _ in calls] == ["refresh_quotes"]


def test_unavailable_optional_projection_clears_exact_consumer_paths_without_erasing_technical_grade():
    import copy
    from app.utils.sector_timing import build_sector_timing_observation
    at = datetime.fromisoformat("2026-10-16T14:50:00+08:00")
    old_sector = {"label": "旧板块 99涨 1跌", "up": 99, "down": 1, "status": "fresh",
                  "source_as_of": "2026-10-16T13:55:00+08:00"}
    all_rows = [{"ts_code": f"{510000+i}.SH", "theme_l1": "synthetic", "grade": "可加仓",
                 "return_5d": 0.02, "sector": old_sector} for i in range(52)]
    timing = build_sector_timing_observation(all_rows, slot_hint="14:45", at=at)
    timing["themes"][0]["market_corroboration"].update(available=True, mean_pct_change=99)
    timing["digest"]["headline"] = "偏强观察synthetic(市+99%)"
    row = {**all_rows[0], "quote": {"source_time": at.isoformat(), "price": 1.1},
           "macd": {"label": "金叉"}, "indicator": {"input_hash": "b"*64}}
    parts = {"overview": {"snapshot_id": "original-id", "generated_at": at.isoformat(),
                         "rows": [row], "sector_timing": timing},
             "details": {row["ts_code"]: {"decision": row, "read_as_of": at.isoformat(),
                         "indicator_input_hash": "b"*64, "indicator_values": {"macd_dif": 0.1},
                         "decision_explanation": {"conclusion": "可加仓", "primary_basis": "技术指标",
                             "evidence_caveats": [], "comparison": {"current_grade": "可加仓"}}}},
             "charts": {row["ts_code"]: {"bars": [{"close": 1.1}]}}}
    before = copy.deepcopy(parts)
    projected = local._project_unavailable_optional(parts, ["sectors", "market_context"], all_rows, at)
    assert parts == before
    for observed in (projected["overview"]["rows"][0], projected["details"][row["ts_code"]]["decision"]):
        assert observed["grade"] == "可加仓" and observed["macd"] == row["macd"]
        assert observed["quote"] == row["quote"]
        assert observed["sector"]["status"] == "unavailable"
        assert observed["sector"]["up"] is None and observed["sector"]["down"] is None
        assert observed["sector"]["source_as_of"] == old_sector["source_as_of"]
    new_timing = projected["overview"]["sector_timing"]
    assert new_timing["themes"][0]["member_count"] == 52
    assert new_timing["themes"][0]["observation"] == timing["themes"][0]["observation"]
    assert new_timing["read_as_of"] == at.isoformat() and new_timing["slot_hint"] == "14:45"
    assert new_timing["themes"][0]["market_corroboration"]["available"] is False
    assert new_timing["themes"][0]["market_corroboration"]["reason_code"] == "optional_not_refreshed"
    assert "99" not in new_timing["digest"]["headline"]
    detail = projected["details"][row["ts_code"]]
    assert detail["indicator_input_hash"] == "b"*64
    assert detail["read_as_of"] == at.isoformat() and detail["decision_explanation"]["conclusion"] == "可加仓"
    assert detail["decision_explanation"]["evidence_caveats"] == [
        "sectors_optional_not_refreshed", "market_context_optional_not_refreshed"]
    assert projected["charts"] == parts["charts"]


def test_sector_is_attached_after_classification_and_cannot_change_grade():
    from app.services.signal_grade_service import classify_row
    values = {"volume_ratio": 2, "ma5": 1.2, "ma10": 1.1, "ma20": 1, "macd_dif": 0.1,
              "macd_dea": 0.05, "kdj_j": 50, "rsi14": 60}
    original = classify_row(values, pct_change=0.01)
    # Classifier inputs contain technical/quote values only; optional sector is
    # attached by SignalGradeService.build after this classification.
    assert classify_row({**values, "sector": {"up": 0, "down": 999}}, pct_change=0.01) == original
    assert classify_row({**values, "sector": {"up": 999, "down": 0}}, pct_change=0.01) == original


def test_actual_export_and_reader_keep_quote_grade_hashes_but_no_skipped_sector(baseline, monkeypatch, tmp_path):
    import copy
    from app.models import QuoteSnapshot, DecisionBoardSnapshot
    from app.services.decision_board_service import DecisionBoardService
    from app.workspace.local_display_contract import verify_bundle_integrity
    from app.workspace.local_display_read import LocalDisplayReader, LocalDisplayStore
    from app.workspace.shadow_bundle import digest
    settings, codes, now, engine = baseline
    with Session(engine) as db, db.begin():
        for item in db.scalars(select(Instrument).where(Instrument.ts_code.in_(codes))):
            db.add(QuoteSnapshot(instrument_id=item.id, quote_time=now, fetched_at=now,
                timestamp_verified=True, is_realtime=True, price=1.1, open=1, high=1.2, low=0.9,
                amount=11, volume=10, pct_change=10, source="sina:hq_sinajs:v1", quality_hash="e"*64))
        db.flush()
        built = DecisionBoardService(settings).refresh(db, generated_at=now)
        source = copy.deepcopy(built.payload)
        for row in source["rows"]:
            row["sector"] = {"label": "旧旁证 99涨 1跌", "up": 99, "down": 1,
                             "source_as_of": (now-timedelta(minutes=55)).isoformat()}
        source["sector_timing"]["digest"]["headline"] = "旧旁证市+99%"
        built.snapshot.payload_json = source
        snapshot_id = built.snapshot.snapshot_id
    actual_read = DecisionBoardService.read_latest
    def reference_read(self, db, **kwargs):
        kwargs.setdefault("at", now)
        return actual_read(self, db, **kwargs)
    monkeypatch.setattr(DecisionBoardService, "read_latest", reference_read)
    bundle = local.export_local_v2(settings, sequence=20, code_sha=SHA, universe=codes, now=now,
        private_research=True, unavailable_parts=["sectors", "market_context"])
    assert verify_bundle_integrity(bundle, now=now)
    assert bundle["manifest"]["parts_hashes"] == {key: digest(value) for key, value in bundle["parts"].items()}
    store = LocalDisplayStore(tmp_path / "receiver")
    store.publish(bundle, now=now)
    reader = LocalDisplayReader(store, code_sha=SHA, config_hash=bundle["manifest"]["config_hash"])
    overview = reader.read_overview(generation=20)
    source_rows = {row["ts_code"]: row for row in source["rows"]}
    for row in overview["rows"]:
        assert row["grade"] == source_rows[row["ts_code"]]["grade"]
        assert row["quote"]["source_time"].startswith("2026-10-16T14:30:00")
        assert row["sector"]["status"] == "unavailable" and row["sector"]["up"] is None
        detail = reader.read_instrument_detail(row["ts_code"], generation=20)
        assert detail["quote"]["price"] == 1.1
        assert detail["decision"]["grade"] == row["grade"]
        assert detail["decision"]["sector"]["status"] == "unavailable"
        assert detail["read_as_of"] == bundle["parts"]["charts"][row["ts_code"]]["as_of"]
        assert "sectors_optional_not_refreshed" in detail["decision_explanation"]["evidence_caveats"]
    assert "99" not in bundle["parts"]["overview"]["sector_timing"]["digest"]["headline"]
    with Session(engine) as db:
        persisted = db.scalar(select(DecisionBoardSnapshot).where(DecisionBoardSnapshot.snapshot_id == snapshot_id))
        assert persisted.payload_json == source
