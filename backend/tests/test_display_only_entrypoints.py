"""Cloud display mode rejects research work before provider/DB side effects."""
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.services.task_service import DisplayOnlyTaskRejected


@pytest.fixture
def display_settings(monkeypatch):
    settings = Settings(_env_file=None, market_provider="mock", workspace_research_source="local_bundle")
    from app.workspace import data_jobs, discovery, worker
    from app import scheduler
    for module in (data_jobs, discovery, worker, scheduler):
        monkeypatch.setattr(module, "get_settings", lambda: settings, raising=False)
    return settings


class NoEffects:
    def __getattr__(self, name):
        raise AssertionError(f"side effect before guard: {name}")


@pytest.mark.parametrize("kind", ["catalog", "onboard", "prepare_history", "factors", "research_outlook", "prices", "api_research"])
def test_data_enqueue_rejects_before_queue_or_provider(display_settings, kind):
    from app.workspace import data_jobs
    from app.workspace.protocol import DataRequest
    if kind == "api_research":
        payload = SimpleNamespace(task=kind)
    else:
        payload = DataRequest(task=kind, codes=["510300.SH"], request_key="display-only-guard-test")
    with pytest.raises(DisplayOnlyTaskRejected):
        data_jobs.enqueue(NoEffects(), payload, None)


def test_worker_execute_cannot_bypass_guard(display_settings, monkeypatch):
    from app.workspace import worker
    monkeypatch.setattr(worker, "session_scope", NoEffects())
    assert worker.execute("a" * 32) == 1


def test_worker_tick_and_claim_are_idle_without_db(display_settings, monkeypatch):
    from app.workspace import data_jobs, worker
    monkeypatch.setattr(worker, "session_scope", NoEffects())
    assert worker.run_once() is False
    assert data_jobs.claim(NoEffects()) is None


def test_scheduler_tick_rejects_before_provider_or_db(display_settings, monkeypatch):
    from app import scheduler
    monkeypatch.setattr(scheduler, "create_provider", NoEffects())
    with pytest.raises(DisplayOnlyTaskRejected):
        scheduler.tick()


@pytest.mark.parametrize("entry", ["catalog", "seed", "factors", "outlook", "discovery", "index_history", "board_queue", "board_refresh", "sr_capture", "sr_compute"])
def test_direct_research_entrypoints_reject_before_db(display_settings, entry):
    from app.workspace import data_seed, discovery, factor_diagnostics, index_history, research_outlook, worker
    from app.services.decision_board_service import DecisionBoardService
    from app.services.support_resistance_service import SupportResistanceService
    calls = {
        "catalog": lambda: worker.sync_catalog(NoEffects(), NoEffects(), settings=display_settings),
        "seed": lambda: data_seed.seed_configured_universe(NoEffects(), display_settings),
        "factors": lambda: factor_diagnostics.run(NoEffects(), display_settings),
        "outlook": lambda: research_outlook.refresh(NoEffects(), display_settings, []),
        "discovery": lambda: discovery.enqueue(NoEffects()),
        "index_history": lambda: index_history.refresh(NoEffects(), display_settings, NoEffects(), "run"),
        "board_queue": lambda: DecisionBoardService(display_settings).enqueue_refresh(NoEffects()),
        "board_refresh": lambda: DecisionBoardService(display_settings).refresh(NoEffects()),
        "sr_capture": lambda: SupportResistanceService(display_settings).capture_for_instruments(NoEffects(), []),
        "sr_compute": lambda: SupportResistanceService(display_settings).compute(NoEffects(), 1),
    }
    with pytest.raises(DisplayOnlyTaskRejected):
        calls[entry]()


def test_runtime_read_does_not_seed_defaults(display_settings, db_session, monkeypatch):
    from app.services.runtime_service import RuntimeService
    service = RuntimeService(display_settings)
    monkeypatch.setattr(service, "ensure_defaults", NoEffects())
    assert service.get_all(db_session)["market_data_tier"] == "usable"


@pytest.mark.parametrize("service_name,method", [
    ("market", "sync_instruments"), ("market", "refresh_daily_bars"),
    ("market", "refresh_quotes"), ("market", "refresh_sector_snapshots"),
    ("market_context", "sync_registry"), ("market_context", "refresh"),
    ("indicators", "refresh_all"), ("forecasts", "refresh_all"),
    ("signals", "refresh_all"), ("news", "refresh"), ("reports", "generate"),
])
def test_domain_writers_cannot_bypass_task_guard(display_settings, service_name, method):
    from app.services.task_service import TaskService
    tasks = TaskService(display_settings, provider=NoEffects())
    try:
        with pytest.raises(DisplayOnlyTaskRejected):
            getattr(getattr(tasks, service_name), method)(NoEffects())
    finally:
        tasks.close()


def test_runtime_default_seeding_itself_is_disabled(display_settings, monkeypatch):
    from app.services.runtime_service import RuntimeService
    RuntimeService(display_settings).ensure_defaults(NoEffects())


def test_api_research_cannot_enqueue_or_bill_in_display_mode(display_settings, monkeypatch):
    from app.workspace import ai_profiles
    monkeypatch.setattr(ai_profiles, "get_settings", lambda: display_settings, raising=False)
    with pytest.raises(DisplayOnlyTaskRejected):
        ai_profiles.enqueue(NoEffects(), 1, "profile", request_key="display-only-research-test")
    assert ai_profiles.execute_ticket("a" * 32) == 1


def test_external_archive_and_minute_sync_are_research_writes(display_settings, monkeypatch):
    from app.workspace import external_research
    from app.services.market_bar_service import MarketBarService
    monkeypatch.setattr(external_research, "get_settings", lambda: display_settings, raising=False)
    with pytest.raises(DisplayOnlyTaskRejected):
        external_research.import_packet(NoEffects(), NoEffects(), "hash", None)
    with pytest.raises(DisplayOnlyTaskRejected):
        MarketBarService(display_settings, NoEffects()).sync_minute_bars(NoEffects())


def test_cli_research_rejects_before_provider_or_session(display_settings, monkeypatch):
    from app import cli
    monkeypatch.setattr(cli, "get_settings", lambda: display_settings)
    monkeypatch.setattr(cli, "TaskService", NoEffects())
    monkeypatch.setattr(cli, "session_scope", NoEffects())
    with pytest.raises(DisplayOnlyTaskRejected):
        cli.run_task("refresh_bars", lookback_days=900, since_hours=72)
    with pytest.raises(DisplayOnlyTaskRejected):
        cli.bootstrap(lookback_days=900)


def test_board_exception_scope_is_exact_and_does_not_leak(display_settings):
    from app.services.research_write_guard import board_maintenance_scope, require_research_write
    # Scope is entered only after TaskService's default-off exception check/audit.
    with board_maintenance_scope(display_settings, "refresh_decision_board"):
        require_research_write(display_settings, "refresh_decision_board")
        require_research_write(display_settings, "support_resistance.compute")
        with pytest.raises(DisplayOnlyTaskRejected):
            require_research_write(display_settings, "capture_latest_quotes")
        with pytest.raises(DisplayOnlyTaskRejected):
            require_research_write(display_settings, "MarketService.refresh_quotes")
    with pytest.raises(DisplayOnlyTaskRejected):
        require_research_write(display_settings, "refresh_decision_board")


def test_board_exception_refuses_when_audit_event_fails(display_settings, monkeypatch):
    from app.services import task_service
    class AuditUnavailable(RuntimeError):
        pass
    def fail_audit(*args, **kwargs):
        raise AuditUnavailable("audit unavailable")
    monkeypatch.setattr(task_service, "emit_event", fail_audit)
    settings = display_settings.model_copy(update={"display_only_allowed_tasks": ["refresh_decision_board"]})
    service = task_service.TaskService(settings)
    try:
        with pytest.raises(AuditUnavailable):
            service.run(NoEffects(), "refresh_decision_board")
    finally:
        service.close()


def test_watchlist_unknown_cannot_fetch_in_display_mode(display_settings, db_session):
    from app.services.watchlist_service import WatchlistService
    with pytest.raises(DisplayOnlyTaskRejected):
        WatchlistService(display_settings, NoEffects()).add(db_session, code="599999.SH")


def test_known_watchlist_and_holding_transactions_remain_available(display_settings, db_session):
    from app.models import Instrument
    from app.services.holding_service import HoldingService
    from app.services.watchlist_service import WatchlistService
    instrument = Instrument(ts_code="599998.SH", symbol="599998", name="Guard ETF", kind="ETF", exchange="SH", enabled=False)
    db_session.add(instrument)
    db_session.flush()
    try:
        entry = WatchlistService(display_settings, NoEffects()).add(db_session, code=instrument.ts_code)
        holding = HoldingService(display_settings).upsert(db_session, ts_code=instrument.ts_code, shares=1, cost_price=1)
        assert entry["ts_code"] == instrument.ts_code and holding.shares == 1
        assert WatchlistService(display_settings).delete(db_session, entry["id"])
    finally:
        db_session.rollback()
