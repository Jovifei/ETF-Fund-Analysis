"""One opt-in per-code recovery preserves provider audit and quality gates."""
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import Base
from app.models import DailyBar, Instrument, ProviderAudit
from app.providers.base import CapabilityUnavailable, MarketProvider, ProviderError
from app.providers.composite import CompositeProvider
from app.providers.types import BarRecord
from app.services.market_service import MarketService
from app.services.task_outcome import normalize_outcome


class PublicAdapter(MarketProvider):
    def __init__(self, name, errors=(), price_only=False):
        self.name, self.errors, self.price_only, self.calls = name, list(errors), price_only, []
    def list_instruments(self, codes=None): return []
    def fetch_spot_quotes(self, codes): return []
    def fetch_daily_bars(self, code, start, end):
        self.calls.append((code, start, end))
        if self.errors:
            error = self.errors.pop(0)
            if error is not None: raise error
        return [BarRecord(ts_code=code, trade_date=end, open=1.2, high=1.3, low=1.1, close=1.2,
            volume=None if self.price_only else 1000, amount=None if self.price_only else 1200,
            source="akshare:sina:v101" if self.price_only else "tencent:stock_zh_a_hist_tx:v101")]


@pytest.fixture
def history_db(monkeypatch):
    monkeypatch.setattr("app.services.settlement.settled_session", lambda *a, **k: date(2026, 10, 15))
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Instrument(ts_code="510300.SH", symbol="510300", name="synthetic")); db.flush()
        yield db
    engine.dispose()


def run(db, fallback, *, enabled=True, provider_name="public_composite", primary=True):
    adapters = ([PublicAdapter("akshare", price_only=True)] if primary else []) + [fallback]
    provider = CompositeProvider(adapters)
    result = MarketService(provider, Settings(_env_file=None, market_provider=provider_name)).refresh_daily_bars(
        db, codes=["510300.SH"], run_id="synthetic-retry", retry_history_once=enabled)
    return normalize_outcome(result), adapters


def test_one_retry_recovers_one_same_source_batch_and_preserves_first_audit(history_db):
    fallback = PublicAdapter("tencent", errors=[ProviderError("synthetic unavailable"), None])
    result, adapters = run(history_db, fallback)
    assert result["status"] == "succeeded" and result["price_only"] == 0
    assert len(fallback.calls) == 2 and fallback.calls[0] == fallback.calls[1]
    assert result["coverage"][0]["attempts"] == 2
    assert result["attempt_counts"] == [{"ts_code": "510300.SH", "attempts": 2}]
    assert history_db.scalar(select(DailyBar)).source == "tencent:stock_zh_a_hist_tx:v101"
    audits = history_db.scalars(select(ProviderAudit).order_by(ProviderAudit.id)).all()
    assert len(audits) == 4
    assert [(a.provider, a.status) for a in audits] == [("akshare", "partial"), ("tencent", "failed"),
        ("akshare", "quality_fallback"), ("tencent", "fallback_used")]


@pytest.mark.parametrize("reason", ["unsupported", "RATE_LIMITED", "PERMISSION_OR_CREDENTIALS_DENIED", "CREDENTIALS_MISSING"])
def test_explicit_restrictions_or_unsupported_do_not_retry(history_db, reason):
    error = CapabilityUnavailable("endpoint absent") if reason == "unsupported" else ProviderError("synthetic restriction", safe_code=reason)
    fallback = PublicAdapter("tencent", errors=[error, None])
    result, _ = run(history_db, fallback)
    assert len(fallback.calls) == 1 and result["status"] == "partial"
    assert result["attempt_counts"][0]["attempts"] == 1


@pytest.mark.parametrize("enabled,provider", [(False, "public_composite"), (True, "mock"), (True, "tushare")])
def test_no_retry_without_opt_in_or_outside_public_scope(history_db, enabled, provider):
    fallback = PublicAdapter("tencent", errors=[ProviderError("synthetic unavailable"), None])
    result, _ = run(history_db, fallback, enabled=enabled, provider_name=provider)
    assert len(fallback.calls) == 1


def test_pure_quantity_unknown_without_failed_trace_does_not_retry(history_db):
    fallback = PublicAdapter("tencent", price_only=True)
    result, _ = run(history_db, fallback)
    assert len(fallback.calls) == 1 and result["status"] == "partial"


def test_second_partial_stays_partial_and_no_third_attempt(history_db):
    fallback = PublicAdapter("tencent", errors=[ProviderError("synthetic one"), ProviderError("synthetic two"), None])
    result, _ = run(history_db, fallback)
    assert len(fallback.calls) == 2 and result["status"] == "partial" and result["price_only"] == 1
    assert history_db.scalar(select(DailyBar)).volume is None
    assert len(history_db.scalars(select(ProviderAudit)).all()) == 4


def test_whole_first_fetch_failure_can_recover_once(history_db):
    fallback = PublicAdapter("tencent", errors=[ProviderError("synthetic unavailable"), None])
    result, _ = run(history_db, fallback, primary=False)
    assert result["status"] == "succeeded" and len(fallback.calls) == 2
    assert [a.status for a in history_db.scalars(select(ProviderAudit).order_by(ProviderAudit.id))] == ["failed", "ok"]


def test_task_layer_forwards_only_explicit_retry_opt_in():
    from app.services.task_service import TaskService
    calls = []
    service = SimpleNamespace(_bind_runtime_provider=lambda *a: None, _ensure_instruments=lambda *a: None,
        market=SimpleNamespace(refresh_daily_bars=lambda *a, **k: calls.append(k) or {}))
    TaskService._execute(service, None, "refresh_bars", "synthetic", retry_history_once=True)
    assert calls[-1]["retry_history_once"] is True
    TaskService._execute(service, None, "refresh_bars", "synthetic")
    assert "retry_history_once" not in calls[-1]


def test_already_complete_same_source_material_does_not_retry(history_db):
    fallback = PublicAdapter("tencent")
    result, _ = run(history_db, fallback)
    assert result["status"] == "succeeded" and len(fallback.calls) == 1
    assert result["attempt_counts"][0]["attempts"] == 1


@pytest.mark.parametrize("code", ["RATE_LIMITED", "PERMISSION_OR_CREDENTIALS_DENIED",
    "CREDENTIALS_MISSING", "ENDPOINT_UNAVAILABLE", "UPSTREAM_REJECTED", "UPSTREAM_HTTP_REJECTED",
    "INVALID_RESPONSE_SCHEMA", "RESPONSE_TOO_LARGE"])
def test_any_explicit_restriction_blocks_retry_even_with_another_generic_failure(history_db, code):
    restricted = PublicAdapter("restricted-public", errors=[ProviderError("synthetic", safe_code=code), None])
    generic = PublicAdapter("tencent", errors=[ProviderError("synthetic generic"), None])
    provider = CompositeProvider([PublicAdapter("akshare", price_only=True), restricted, generic])
    result = MarketService(provider, Settings(_env_file=None, market_provider="public_composite")).refresh_daily_bars(
        history_db, codes=["510300.SH"], retry_history_once=True)
    assert normalize_outcome(result)["status"] == "partial"
    assert len(restricted.calls) == len(generic.calls) == 1
