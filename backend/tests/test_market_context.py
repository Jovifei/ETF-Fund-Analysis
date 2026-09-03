from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from app.core.config import Settings
from app.market_context.contracts import (
    ContextKind,
    FreshnessStatus,
    MarketContextItem,
    MarketContextObservation,
    RegistryConfig,
    VerificationStatus,
)
from app.models import EventLog, MarketContextRegistry, MarketContextSnapshot, TaskRun
from app.providers.base import CapabilityUnavailable, MarketProvider, ProviderError
from app.providers.composite import CompositeProvider
from app.providers.mock import MockProvider
from app.providers.types import BarRecord, InstrumentRecord, QuoteRecord
from pydantic import ValidationError
from sqlalchemy import CheckConstraint, create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "market_context.json"


def _observation_payload(**updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "context_id": "us-sp500",
        "source_symbol": "INDEX:SP500",
        "observed_value": 100.0,
        "today_pct_change": 0.1,
        "source": "feed",
        "source_timestamp": datetime(2026, 8, 28, 9, 30, tzinfo=UTC),
        "fetched_at": datetime(2026, 8, 28, 9, 31, tzinfo=UTC),
        "freshness": FreshnessStatus.FRESH,
        "verification_status": VerificationStatus.VERIFIED,
        "is_mock": False,
    }
    payload.update(updates)
    return payload


def _insert_sqlite_registry(engine, **updates: object) -> None:
    values: dict[str, object] = {
        "context_id": "db-index",
        "label": "DB index",
        "region": "United States",
        "context_kind": "index",
        "source_symbol": None,
        "display_code": None,
        "is_tradable_proxy": False,
        "enabled": False,
        "display_order": 1,
        "source_priority": "[]",
        "freshness_rule": "provider_defined",
        "verification_status": "unverified",
    }
    values.update(updates)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO market_context_registry "
                "(context_id, label, region, context_kind, source_symbol, display_code, "
                "is_tradable_proxy, enabled, display_order, source_priority, freshness_rule, "
                "verification_status) VALUES (:context_id, :label, :region, :context_kind, "
                ":source_symbol, :display_code, :is_tradable_proxy, :enabled, :display_order, "
                ":source_priority, :freshness_rule, :verification_status)"
            ),
            values,
        )


def _sqlite_market_context_engine():
    from app.db.base import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
    _insert_sqlite_registry(engine)
    return engine


def _insert_sqlite_snapshot(engine, **updates: object) -> None:
    values: dict[str, object] = {
        "registry_id": 1,
        "source_symbol": "INDEX:SP500",
        "observed_value": 100.0,
        "today_pct_change": 0.1,
        "price": None,
        "source": "feed",
        "source_timestamp": "2026-08-28 09:30:00.000000",
        "fetched_at": "2026-08-28 09:31:00.000000",
        "freshness": "fresh",
        "verification_status": "verified",
        "is_mock": False,
        "degraded_reason": None,
    }
    values.update(updates)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO market_context_snapshots "
                "(registry_id, source_symbol, observed_value, today_pct_change, price, source, source_timestamp, "
                "fetched_at, freshness, verification_status, is_mock, degraded_reason) VALUES "
                "(:registry_id, :source_symbol, :observed_value, :today_pct_change, :price, :source, "
                ":source_timestamp, :fetched_at, :freshness, :verification_status, :is_mock, "
                ":degraded_reason)"
            ),
            values,
        )


def test_default_registry_has_exact_six_renderable_items_and_distinct_index_ids() -> None:
    registry = Settings(_env_file=None).load_market_context()

    assert len(registry.items) == 9
    assert {item.context_id for item in registry.items} == {
        "china-sector-breadth",
        "cn-shanghai-composite",
        "cn-csi300",
        "cn-csi-all",
        "us-sp500",
        "us-nasdaq-composite",
        "us-nasdaq-100",
        "china-semiconductor-etf",
        "korea-semiconductor-etf",
    }
    assert [item.display_order for item in registry.items] == list(range(1, 10))
    assert len({item.display_order for item in registry.items}) == 9
    assert registry.item_by_id("us-sp500").context_id != registry.item_by_id("us-nasdaq-composite").context_id
    assert all(item.label for item in registry.items)
    # A股/美股大盘指数与可交易代理默认启用（真实数据源场景），板块广度与韩代保持禁用
    assert all(item.enabled for item in registry.items if item.context_id != "china-sector-breadth" and item.context_id != "korea-semiconductor-etf")


def test_registry_rejects_duplicate_context_ids_orders_and_unknown_fields() -> None:
    item = MarketContextItem(
        context_id="one",
        label="One",
        region="china",
        context_kind=ContextKind.INDEX,
        display_order=1,
        verification_status=VerificationStatus.UNVERIFIED,
        enabled=False,
    )
    with pytest.raises(ValidationError, match="context_id"):
        RegistryConfig(items=(item, item.model_copy(update={"display_order": 2})))
    with pytest.raises(ValidationError, match="display_order"):
        RegistryConfig(items=(item, item.model_copy(update={"context_id": "two"})))
    with pytest.raises(ValidationError, match="Extra"):
        MarketContextItem.model_validate({**item.model_dump(), "unexpected": True})


def test_registry_gates_enabled_and_tradable_proxy_verification() -> None:
    base = {
        "context_id": "proxy",
        "label": "Proxy",
        "region": "china",
        "context_kind": ContextKind.TRADABLE_PROXY,
        "display_order": 1,
        "is_tradable_proxy": True,
    }
    with pytest.raises(ValidationError, match="verified"):
        MarketContextItem.model_validate({**base, "enabled": True, "verification_status": "unverified"})
    with pytest.raises(ValidationError, match="source_symbol"):
        MarketContextItem.model_validate({**base, "enabled": True, "verification_status": "verified"})
    with pytest.raises(ValidationError, match="display_code"):
        MarketContextItem.model_validate(
            {
                **base,
                "enabled": True,
                "verification_status": "verified",
                "source_symbol": "verified-symbol",
            }
        )
    with pytest.raises(ValidationError, match="unverified"):
        MarketContextItem.model_validate(
            {
                **base,
                "source_symbol": "invented-symbol",
                "display_code": "invented-code",
                "verification_status": "unverified",
            }
        )


def test_context_kind_and_proxy_flag_must_be_equivalent_in_both_directions() -> None:
    with pytest.raises(ValidationError, match="context_kind"):
        MarketContextItem(
            context_id="proxy-kind-without-flag",
            label="Proxy",
            region="china",
            context_kind=ContextKind.TRADABLE_PROXY,
            is_tradable_proxy=False,
            display_order=1,
        )
    with pytest.raises(ValidationError, match="context_kind"):
        MarketContextItem(
            context_id="flag-without-proxy-kind",
            label="Index",
            region="china",
            context_kind=ContextKind.INDEX,
            is_tradable_proxy=True,
            display_order=1,
        )


@pytest.mark.parametrize("field", ["enabled", "is_tradable_proxy"])
@pytest.mark.parametrize("coerced_value", [0, 1, "false", "true"])
def test_registry_booleans_reject_integer_and_string_coercion(field: str, coerced_value: object) -> None:
    item = {
        "context_id": "strict-bool",
        "label": "Strict",
        "region": "china",
        "context_kind": ContextKind.INDEX,
        "display_order": 1,
        field: coerced_value,
    }
    with pytest.raises(ValidationError):
        MarketContextItem.model_validate(item)


@pytest.mark.parametrize("coerced_value", [0, 1, "false", "true"])
def test_observation_mock_boolean_rejects_integer_and_string_coercion(coerced_value: object) -> None:
    with pytest.raises(ValidationError):
        MarketContextObservation.model_validate(
            {
                "context_id": "us-sp500",
                "observed_value": 100.0,
                "today_pct_change": 0.1,
                "source": "feed",
                "source_timestamp": datetime(2026, 8, 28, 9, 30, tzinfo=UTC),
                "fetched_at": datetime(2026, 8, 28, 9, 31, tzinfo=UTC),
                "is_mock": coerced_value,
            }
        )


def test_market_context_checks_use_portable_boolean_semantics() -> None:
    constraints = list(MarketContextRegistry.__table__.constraints)
    expressions = "\n".join(
        str(constraint.sqltext)
        for constraint in constraints
        if isinstance(constraint, CheckConstraint)
    )
    assert "enabled = 0" not in expressions
    assert "is_tradable_proxy = 0" not in expressions

    migration = (
        PROJECT_ROOT / "backend" / "alembic" / "versions" / "a2b3c4d5e6f7_market_context.py"
    ).read_text(encoding="utf-8")
    assert "enabled = 0" not in migration
    assert "is_tradable_proxy = 0" not in migration
    assert "NOT enabled" in migration
    assert "NOT is_tradable_proxy" in migration


def test_default_china_and_korea_proxies_are_disabled_unverified_and_null() -> None:
    raw = json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    proxies = {item["context_id"]: item for item in raw["items"] if item["is_tradable_proxy"]}
    assert set(proxies) == {
        "china-semiconductor-etf",
        "korea-semiconductor-etf",
    }
    # China proxy 已启用并配置真实可交易 ETF（512480 半导体ETF）；Korea proxy 无数据源故保持禁用。
    china = proxies["china-semiconductor-etf"]
    assert china["enabled"] is True
    assert china["verification_status"] == "verified"
    assert china["source_symbol"] == "512480"
    assert china["display_code"] == "512480.SH"
    korea = proxies["korea-semiconductor-etf"]
    assert korea["enabled"] is False
    assert korea["verification_status"] == "unverified"
    assert korea["source_symbol"] is None
    assert korea["display_code"] is None


def test_settings_market_context_loader_returns_immutable_typed_registry_and_rejects_bad_json(tmp_path: Path) -> None:
    good_path = tmp_path / "market-context.json"
    good_path.write_text(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    registry = Settings(_env_file=None, market_context_path=good_path).load_market_context()
    assert isinstance(registry, RegistryConfig)
    with pytest.raises(ValidationError):
        registry.items[0].label = "mutated"  # type: ignore[misc]

    bad_path = tmp_path / "bad-market-context.json"
    bad_data = json.loads(good_path.read_text(encoding="utf-8"))
    bad_data["items"][0]["unknown"] = "reject"
    bad_path.write_text(json.dumps(bad_data), encoding="utf-8")
    with pytest.raises(ValidationError, match="Extra"):
        Settings(_env_file=None, market_context_path=bad_path).load_market_context()


def test_market_context_observation_is_typed_finite_and_keeps_source_and_fetch_timestamps_separate() -> None:
    source_time = datetime(2026, 8, 28, 9, 30, tzinfo=UTC)
    fetched_at = source_time + timedelta(seconds=7)
    observation = MarketContextObservation(
        context_id="us-sp500",
        source_symbol="INDEX:SP500",
        observed_value=5_432.10,
        today_pct_change=-0.42,
        price=None,
        source="verified-feed",
        source_timestamp=source_time,
        fetched_at=fetched_at,
        freshness=FreshnessStatus.FRESH,
        verification_status=VerificationStatus.VERIFIED,
        is_mock=False,
    )
    assert observation.today_pct_change == -0.42
    assert observation.source_timestamp != observation.fetched_at
    assert observation.source_timestamp.tzinfo is not None
    with pytest.raises(ValidationError):
        MarketContextObservation.model_validate({**observation.model_dump(), "observed_value": float("nan")})
    with pytest.raises(ValidationError, match="extra"):
        MarketContextObservation.model_validate({**observation.model_dump(), "credentials": "secret"})


def test_mock_observation_requires_unverified_degraded_reasoned_provenance() -> None:
    valid = MarketContextObservation.model_validate(
        _observation_payload(
            freshness=FreshnessStatus.DEGRADED,
            verification_status=VerificationStatus.UNVERIFIED,
            is_mock=True,
            degraded_reason="synthetic test observation",
        )
    )
    assert valid.is_mock is True
    invalid_payloads = (
        {"verification_status": VerificationStatus.VERIFIED, "freshness": FreshnessStatus.DEGRADED, "degraded_reason": "mock"},
        {"verification_status": VerificationStatus.UNVERIFIED, "freshness": FreshnessStatus.FRESH, "degraded_reason": "mock"},
        {"verification_status": VerificationStatus.UNVERIFIED, "freshness": FreshnessStatus.DEGRADED, "degraded_reason": ""},
    )
    for updates in invalid_payloads:
        with pytest.raises(ValidationError):
            MarketContextObservation.model_validate(_observation_payload(is_mock=True, **updates))


@pytest.mark.parametrize("freshness", [FreshnessStatus.FRESH, FreshnessStatus.STALE])
def test_fresh_or_stale_observation_requires_no_degraded_reason(freshness: FreshnessStatus) -> None:
    with pytest.raises(ValidationError):
        MarketContextObservation.model_validate(
            _observation_payload(freshness=freshness, degraded_reason="reason")
        )
    valid = MarketContextObservation.model_validate(
        _observation_payload(freshness=freshness, degraded_reason=None)
    )
    assert valid.degraded_reason is None


def test_sqlite_freshness_reason_check_accepts_only_coherent_pairs() -> None:
    engine = _sqlite_market_context_engine()
    _insert_sqlite_snapshot(
        engine,
        source_timestamp="2026-08-28 09:30:00.000000",
        fetched_at="2026-08-28 09:30:01.000000",
        freshness="fresh",
        degraded_reason=None,
    )
    _insert_sqlite_snapshot(
        engine,
        source_timestamp="2026-08-28 09:31:00.000000",
        fetched_at="2026-08-28 09:31:01.000000",
        freshness="stale",
        degraded_reason=None,
    )
    _insert_sqlite_snapshot(
        engine,
        source_timestamp="2026-08-28 09:32:00.000000",
        fetched_at="2026-08-28 09:32:01.000000",
        freshness="degraded",
        degraded_reason="provider timeout",
    )
    _insert_sqlite_snapshot(
        engine,
        source_timestamp="2026-08-28 09:33:00.000000",
        fetched_at="2026-08-28 09:33:01.000000",
        freshness="unavailable",
        degraded_reason="capability unavailable",
    )
    with pytest.raises(IntegrityError):
        _insert_sqlite_snapshot(
            engine,
            source_timestamp="2026-08-28 09:34:00.000000",
            fetched_at="2026-08-28 09:34:01.000000",
            freshness="fresh",
            degraded_reason="must be absent",
        )
    with pytest.raises(IntegrityError):
        _insert_sqlite_snapshot(
            engine,
            source_timestamp="2026-08-28 09:35:00.000000",
            fetched_at="2026-08-28 09:35:01.000000",
            freshness="stale",
            degraded_reason="must be absent",
        )


def test_context_timestamps_require_timezone_and_source_before_fetch() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        MarketContextObservation.model_validate(
            _observation_payload(source_timestamp=datetime(2026, 8, 28, 9, 30))
        )
    with pytest.raises(ValidationError, match="timezone"):
        MarketContextObservation.model_validate(
            _observation_payload(fetched_at=datetime(2026, 8, 28, 9, 31))
        )
    normalized = MarketContextObservation.model_validate(
        _observation_payload(
            source_timestamp=datetime(2026, 8, 28, 1, 30, tzinfo=timezone(timedelta(hours=-8))),
            fetched_at=datetime(2026, 8, 28, 1, 31, tzinfo=timezone(timedelta(hours=-8))),
        )
    )
    assert normalized.source_timestamp.tzinfo is UTC
    assert normalized.fetched_at.tzinfo is UTC
    with pytest.raises(ValidationError, match="source_timestamp"):
        MarketContextObservation.model_validate(
            _observation_payload(
                source_timestamp=datetime(2026, 8, 28, 9, 32, tzinfo=UTC),
                fetched_at=datetime(2026, 8, 28, 9, 31, tzinfo=UTC),
            )
        )


def test_market_context_sqlite_checks_reject_invalid_provenance_times_and_duplicates() -> None:
    engine = _sqlite_market_context_engine()
    with pytest.raises(IntegrityError):
        _insert_sqlite_snapshot(engine, verification_status="verified", freshness="degraded", is_mock=True, degraded_reason="mock")
    with pytest.raises(IntegrityError):
        _insert_sqlite_snapshot(engine, verification_status="unverified", freshness="fresh", is_mock=True, degraded_reason="mock")
    with pytest.raises(IntegrityError):
        _insert_sqlite_snapshot(engine, verification_status="unverified", freshness="degraded", is_mock=True, degraded_reason="")
    registry_engine = create_engine("sqlite:///:memory:")
    from app.db.base import Base

    Base.metadata.create_all(registry_engine)
    with pytest.raises(IntegrityError):
        _insert_sqlite_registry(registry_engine, display_code="not-allowed")
    with pytest.raises(IntegrityError):
        _insert_sqlite_snapshot(engine, freshness="degraded", degraded_reason="")
    with pytest.raises(IntegrityError):
        _insert_sqlite_snapshot(engine, freshness="degraded", degraded_reason="x" * 513)
    with pytest.raises(IntegrityError):
        _insert_sqlite_snapshot(
            engine,
            source_timestamp="2026-08-28 09:32:00.000000",
            fetched_at="2026-08-28 09:31:00.000000",
        )
    _insert_sqlite_snapshot(engine)
    with pytest.raises(IntegrityError):
        _insert_sqlite_snapshot(engine)


def test_registry_context_id_uses_unique_constraint_without_redundant_index() -> None:
    indexes = {index.name for index in MarketContextRegistry.__table__.indexes}
    assert "ix_market_context_registry_context_id" not in indexes


class _NoContextProvider(MarketProvider):
    def list_instruments(self, codes: list[str] | None = None) -> list[InstrumentRecord]:
        return []

    def fetch_daily_bars(self, ts_code, start_date, end_date) -> list[BarRecord]:
        return []

    def fetch_spot_quotes(self, codes: list[str]) -> list[QuoteRecord]:
        return []


def test_base_provider_context_capability_is_unavailable_and_never_an_etf_quote() -> None:
    with pytest.raises(CapabilityUnavailable, match="market context"):
        _NoContextProvider().fetch_market_context([])


def test_market_context_orm_registry_and_snapshot_constraints_are_declared() -> None:
    registry_constraints = {constraint.name for constraint in MarketContextRegistry.__table__.constraints}
    snapshot_constraints = {constraint.name for constraint in MarketContextSnapshot.__table__.constraints}
    assert "uq_market_context_registry_context_id" in registry_constraints
    assert "uq_market_context_registry_display_order" in registry_constraints
    assert "uq_market_context_snapshot_idempotency" in snapshot_constraints
    foreign_keys = list(inspect(MarketContextSnapshot).columns.registry_id.foreign_keys)
    assert len(foreign_keys) == 1
    assert foreign_keys[0].target_fullname == "market_context_registry.id"
    assert {column.name for column in MarketContextSnapshot.__table__.columns} >= {
        "source_symbol",
        "observed_value",
        "today_pct_change",
        "price",
        "source",
        "source_timestamp",
        "fetched_at",
        "freshness",
        "verification_status",
        "is_mock",
        "degraded_reason",
    }


def test_snapshot_source_symbol_is_required_and_part_of_sqlite_idempotency_key() -> None:
    engine = _sqlite_market_context_engine()
    _insert_sqlite_snapshot(engine, source_symbol="INDEX:A")
    _insert_sqlite_snapshot(engine, source_symbol="INDEX:B")
    with pytest.raises(IntegrityError):
        _insert_sqlite_snapshot(engine, source_symbol="INDEX:B")
    with pytest.raises(IntegrityError):
        _insert_sqlite_snapshot(engine, source_symbol=None)
    columns = {column["name"] for column in inspect(engine).get_columns("market_context_snapshots")}
    assert "source_symbol" in columns
    unique_constraints = inspect(engine).get_unique_constraints("market_context_snapshots")
    assert any(
        constraint["column_names"] == ["registry_id", "source_symbol", "source", "source_timestamp"]
        for constraint in unique_constraints
    )
    engine.dispose()


def test_snapshot_source_symbol_sqlite_constraint_rejects_blank_and_overlong_values() -> None:
    engine = _sqlite_market_context_engine()
    for invalid_symbol in ("", "   ", "x" * 129):
        with pytest.raises(IntegrityError):
            _insert_sqlite_snapshot(engine, source_symbol=invalid_symbol)
    _insert_sqlite_snapshot(engine, source_symbol="x" * 128)
    engine.dispose()


def test_market_context_migration_has_expected_revision_chain() -> None:
    migration = (PROJECT_ROOT / "backend" / "alembic" / "versions" / "a2b3c4d5e6f7_market_context.py").read_text(
        encoding="utf-8"
    )
    assert 'revision: str = "a2b3c4d5e6f7"' in migration
    assert 'down_revision: str | None = "9f1c2b3a4d5e"' in migration
    assert 'sa.Column("source_symbol", sa.String(length=128), nullable=False)' in migration
    assert '"registry_id", "source_symbol", "source", "source_timestamp"' in migration
    assert "def upgrade" in migration and "def downgrade" in migration


def test_sync_registry_reconciles_swapped_configured_orders_with_historical_rows() -> None:
    from app.services.market_context_service import MarketContextService
    from sqlalchemy.orm import Session

    engine = _sqlite_market_context_engine()
    _insert_sqlite_registry(engine, context_id="configured-a", display_order=2)
    _insert_sqlite_registry(engine, context_id="configured-b", display_order=3)
    _insert_sqlite_registry(engine, context_id="historical", display_order=4)
    _insert_sqlite_snapshot(engine, registry_id=1)
    _insert_sqlite_snapshot(engine, registry_id=4)
    config = RegistryConfig(
        items=(
            MarketContextItem(
                context_id="configured-b",
                label="Configured B",
                region="United States",
                context_kind=ContextKind.INDEX,
                display_order=2,
            ),
            MarketContextItem(
                context_id="configured-a",
                label="Configured A",
                region="United States",
                context_kind=ContextKind.INDEX,
                display_order=3,
            ),
        )
    )

    with Session(engine) as db:
        result = MarketContextService(_NoContextProvider()).sync_registry(db, config=config)
        rows = {
            row.context_id: row
            for row in db.scalars(select(MarketContextRegistry).order_by(MarketContextRegistry.context_id)).all()
        }

        assert result == {"created": 0, "updated": 2, "stale": 2, "total": 4}
        assert {context_id: row.display_order for context_id, row in rows.items()} == {
            "configured-a": 3,
            "configured-b": 2,
            "db-index": 10_000,
            "historical": 9_999,
        }
        assert rows["db-index"].enabled is False
        assert rows["historical"].enabled is False
        assert rows["historical"].source_symbol is None
        assert rows["historical"].display_code is None
    engine.dispose()


@pytest.mark.parametrize(
    ("enabled", "verification_status", "source_symbol"),
    [
        (False, VerificationStatus.VERIFIED, "INDEX:VERIFIED"),
        (False, VerificationStatus.UNVERIFIED, None),
    ],
)
def test_latest_view_hides_historical_snapshot_for_unavailable_configured_row(
    enabled: bool,
    verification_status: VerificationStatus,
    source_symbol: str | None,
) -> None:
    from app.services.market_context_service import MarketContextService
    from sqlalchemy.orm import Session

    engine = _sqlite_market_context_engine()
    initial = _verified_context_config()
    disabled = RegistryConfig(
        items=(
            initial.items[0].model_copy(
                update={
                    "enabled": enabled,
                    "verification_status": verification_status,
                    "source_symbol": source_symbol,
                }
            ),
        )
    )
    with Session(engine) as db:
        service = MarketContextService(_NoContextProvider())
        service.sync_registry(db, config=initial)
        row = db.scalar(select(MarketContextRegistry).where(MarketContextRegistry.context_id == "verified-index"))
        assert row is not None
        db.add(
            MarketContextSnapshot(
                registry_id=row.id,
                source_symbol="INDEX:VERIFIED",
                observed_value=100.0,
                today_pct_change=0.1,
                source="verified-feed",
                source_timestamp=datetime(2026, 8, 28, 9, 30, tzinfo=UTC),
                fetched_at=datetime(2026, 8, 28, 9, 31, tzinfo=UTC),
                freshness=FreshnessStatus.FRESH.value,
                verification_status=VerificationStatus.VERIFIED.value,
                is_mock=False,
            )
        )
        db.flush()
        service.sync_registry(db, config=disabled)

        view = service.latest_view(db)[0]
        assert view["observation"] is None
        assert view["status"] == FreshnessStatus.UNAVAILABLE.value
        assert view["freshness"] == FreshnessStatus.UNAVAILABLE.value
        assert db.scalar(select(MarketContextSnapshot.id)) is not None
    engine.dispose()


def test_latest_view_marks_eligible_configured_row_without_snapshot_unavailable() -> None:
    from app.services.market_context_service import MarketContextService
    from sqlalchemy.orm import Session

    engine = _sqlite_market_context_engine()
    config = _verified_context_config()
    with Session(engine) as db:
        service = MarketContextService(_NoContextProvider())
        service.sync_registry(db, config=config)

        view = service.latest_view(db)[0]
        assert view["observation"] is None
        assert view["status"] == FreshnessStatus.UNAVAILABLE.value
        assert view["freshness"] == FreshnessStatus.UNAVAILABLE.value
        assert view["verification_status"] == VerificationStatus.VERIFIED.value
    engine.dispose()


def test_source_symbol_change_hides_old_snapshot_and_allows_same_time_new_snapshot() -> None:
    from app.services.market_context_service import MarketContextService
    from sqlalchemy.orm import Session

    engine = _sqlite_market_context_engine()
    base_config = _verified_context_config()
    config_a = RegistryConfig(
        items=(base_config.items[0].model_copy(update={"source_symbol": "INDEX:A"}),)
    )
    config_b = RegistryConfig(
        items=(config_a.items[0].model_copy(update={"source_symbol": "INDEX:B"}),)
    )
    source_time = datetime(2026, 8, 28, 9, 30, tzinfo=UTC)
    observation_a = MarketContextObservation(
        context_id="verified-index",
        source_symbol="INDEX:A",
        observed_value=1,
        today_pct_change=0.1,
        source="fake",
        source_timestamp=source_time,
        fetched_at=source_time + timedelta(seconds=1),
        freshness=FreshnessStatus.FRESH,
        verification_status=VerificationStatus.VERIFIED,
    )
    observation_b = observation_a.model_copy(update={"source_symbol": "INDEX:B"})
    provider = _ContextCountingProvider(rows=[observation_a])
    with Session(engine) as db:
        service = MarketContextService(provider)
        assert service.refresh(db, config=config_a)["inserted"] == 1
        service.sync_registry(db, config=config_b)
        unavailable = service.latest_view(db)[0]
        assert unavailable["observation"] is None
        assert unavailable["status"] == FreshnessStatus.UNAVAILABLE.value
        assert unavailable["source_symbol"] == "INDEX:B"

        provider.rows = [observation_b]
        assert service.refresh(db, config=config_b)["inserted"] == 1
        current = service.latest_view(db)[0]
        assert current["observation"]["source"] == "fake"
        assert current["source_symbol"] == "INDEX:B"
        assert len(db.scalars(select(MarketContextSnapshot)).all()) == 2
    engine.dispose()


def test_sync_registry_allocates_historical_order_around_configured_order_10000() -> None:
    from app.services.market_context_service import MarketContextService
    from sqlalchemy.orm import Session

    engine = _sqlite_market_context_engine()
    _insert_sqlite_registry(engine, context_id="configured", display_order=2)
    _insert_sqlite_registry(engine, context_id="historical", display_order=3)
    _insert_sqlite_snapshot(engine, registry_id=3)
    config = RegistryConfig(
        items=(
            MarketContextItem(
                context_id="configured",
                label="Configured",
                region="United States",
                context_kind=ContextKind.INDEX,
                display_order=10_000,
            ),
        )
    )

    with Session(engine) as db:
        MarketContextService(_NoContextProvider()).sync_registry(db, config=config)
        rows = {
            row.context_id: row.display_order
            for row in db.scalars(select(MarketContextRegistry)).all()
        }
        assert rows == {"configured": 10_000, "historical": 9_999}
    engine.dispose()


class _ContextCountingProvider(_NoContextProvider):
    name = "counting"

    def __init__(self, rows=None, error: Exception | None = None) -> None:
        self.rows = rows
        self.error = error
        self.calls = 0

    def fetch_market_context(self, requests):
        self.calls += 1
        if self.error:
            raise self.error
        return list(self.rows or [])


def test_nonmock_unverified_fresh_observation_is_rejected_for_verified_registry() -> None:
    from app.models import ProviderAudit
    from app.services.market_context_service import MarketContextObservationError, MarketContextService

    engine, db = _context_session()
    config = _verified_context_config()
    row = MarketContextObservation.model_validate(
        _observation_payload(
            context_id="verified-index",
            source_symbol="INDEX:VERIFIED",
            verification_status=VerificationStatus.UNVERIFIED,
            freshness=FreshnessStatus.FRESH,
            is_mock=False,
        )
    )
    provider = _ContextCountingProvider(rows=[row])

    with pytest.raises(MarketContextObservationError, match="verification"):
        MarketContextService(provider).refresh(db, config=config, run_id="unverified-real")
    audits = db.scalars(select(ProviderAudit)).all()
    assert audits and all(audit.status == "failed" for audit in audits)
    assert db.scalars(select(MarketContextSnapshot)).all() == []
    db.close()
    engine.dispose()


def test_composite_capability_unavailable_is_unsupported_not_failed() -> None:
    composite = CompositeProvider([_NoContextProvider()])

    with pytest.raises(CapabilityUnavailable):
        composite.fetch_market_context([])
    assert len(composite.last_trace) == 1
    assert composite.last_trace[0].status == "unsupported"
    assert composite.last_trace[0].reason == "CapabilityUnavailable"


def test_composite_failure_logging_and_trace_are_sanitized(caplog: pytest.LogCaptureFixture) -> None:
    class _SecretFailureProvider(_NoContextProvider):
        name = "secret-failure"

        def fetch_market_context(self, requests):
            del requests
            raise RuntimeError("https://user:password@example.test/feed?token=secret-response")

    composite = CompositeProvider([_SecretFailureProvider()])
    with caplog.at_level(logging.WARNING):
        with pytest.raises(ProviderError):
            composite.fetch_market_context([])

    assert "password" not in caplog.text
    assert "secret-response" not in caplog.text
    assert composite.last_trace[0].reason == "RuntimeError"


def test_market_context_snapshot_duplicate_is_idempotent_and_outer_transaction_remains_usable() -> None:
    from app.services.market_context_service import MarketContextService

    engine, db = _context_session()
    config = _verified_context_config()
    source_time = datetime(2026, 8, 28, 9, 30, tzinfo=UTC)
    observation = MarketContextObservation(
        context_id="verified-index",
        source_symbol="INDEX:VERIFIED",
        observed_value=1,
        today_pct_change=0.1,
        source="fake",
        source_timestamp=source_time,
        fetched_at=source_time + timedelta(seconds=1),
        freshness=FreshnessStatus.FRESH,
        verification_status=VerificationStatus.VERIFIED,
    )
    service = MarketContextService(_NoContextProvider())
    service.sync_registry(db, config=config)
    rows = {row.context_id: row for row in db.scalars(select(MarketContextRegistry)).all()}
    assert rows["verified-index"].id is not None

    assert service._persist_observations(db, [observation], rows) == 1
    db.add(
        MarketContextRegistry(
            context_id="outer-work",
            label="Outer work",
            region="United States",
            context_kind=ContextKind.INDEX.value,
            display_order=9_999,
            source_priority=[],
            freshness_rule="provider_defined",
            verification_status=VerificationStatus.UNVERIFIED.value,
        )
    )
    assert service._persist_observations(db, [observation], rows) == 0
    db.flush()
    assert db.scalar(select(MarketContextRegistry).where(MarketContextRegistry.context_id == "outer-work")) is not None
    db.close()
    engine.dispose()


def _context_session():
    from sqlalchemy.orm import Session

    engine = _sqlite_market_context_engine()
    return engine, Session(engine)


def _verified_context_config() -> RegistryConfig:
    item = MarketContextItem(
        context_id="verified-index",
        label="Verified index",
        region="United States",
        context_kind=ContextKind.INDEX,
        source_symbol="INDEX:VERIFIED",
        enabled=True,
        display_order=1,
        source_priority=(),
        verification_status=VerificationStatus.VERIFIED,
    )
    return RegistryConfig(items=(item,))


def test_source_priority_fails_closed_when_provider_order_cannot_honor_it() -> None:
    from app.services.market_context_service import MarketContextError, MarketContextService

    engine, db = _context_session()
    config = RegistryConfig(
        items=(_verified_context_config().items[0].model_copy(update={"source_priority": ("not-base",)}),)
    )
    service = MarketContextService(_NoContextProvider())
    service.sync_registry(db, config=config)

    with pytest.raises(MarketContextError, match="source_priority"):
        service.build_requests(db)
    db.close()
    engine.dispose()


def test_market_context_refresh_keeps_disabled_registry_visible_without_provider_call() -> None:
    from app.services.market_context_service import MarketContextService

    engine, db = _context_session()
    provider = _ContextCountingProvider()
    service = MarketContextService(provider)
    disabled = RegistryConfig(
        items=(
            MarketContextItem(
                context_id="china-sector-breadth",
                label="板块广度",
                region="China",
                context_kind=ContextKind.SECTOR_BREADTH,
                enabled=False,
                display_order=1,
                verification_status=VerificationStatus.UNVERIFIED,
            ),
            MarketContextItem(
                context_id="us-sp500-disabled",
                label="S&P 500 (disabled)",
                region="United States",
                context_kind=ContextKind.INDEX,
                enabled=False,
                display_order=2,
                verification_status=VerificationStatus.UNVERIFIED,
            ),
        )
    )
    result = service.refresh(db, config=disabled)
    view = service.latest_view(db)

    assert result["requested"] == 0
    assert result["provider_calls"] == 0
    assert provider.calls == 0
    assert len(view) == 2
    assert all(
        row["observation"] is None
        and row["status"] == FreshnessStatus.UNAVAILABLE.value
        and row["freshness"] == FreshnessStatus.UNAVAILABLE.value
        for row in view
    )
    db.close()
    engine.dispose()


def test_refresh_market_context_task_reports_bounded_counts_and_same_run_event(tmp_path: Path) -> None:
    from app.services.market_context_service import MarketContextService
    from app.services.task_service import TaskService

    engine, db = _context_session()
    config_path = tmp_path / "market-context.json"
    # 用一个全禁用的显式 registry，验证"无 eligible 卡片 → 不调用 provider、无观测"的语义
    config_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "context_id": "china-sector-breadth",
                        "label": "板块广度",
                        "region": "China",
                        "context_kind": "sector_breadth",
                        "source_symbol": None,
                        "enabled": False,
                        "display_order": 1,
                        "source_priority": [],
                        "freshness_rule": "provider_defined",
                        "verification_status": "unverified",
                    },
                    {
                        "context_id": "us-sp500-disabled",
                        "label": "S&P 500 (disabled)",
                        "region": "United States",
                        "context_kind": "index",
                        "source_symbol": None,
                        "enabled": False,
                        "display_order": 2,
                        "source_priority": [],
                        "freshness_rule": "provider_defined",
                        "verification_status": "unverified",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    settings = Settings(_env_file=None, market_context_path=config_path)
    provider = _ContextCountingProvider()
    tasks = TaskService(settings)
    tasks.market_context = MarketContextService(provider, settings)
    result = tasks.run(db, "refresh_market_context", run_id="market-context-task")

    assert result["status"] == "succeeded"
    assert result["configured"] == 2
    assert result["eligible"] == 0
    assert result["observed"] == 0
    assert result["inserted"] == 0
    assert result["missing"] == 0
    assert result["mock"] == 0
    assert result["degraded"] == 0
    assert result["unsupported"] == 0
    assert provider.calls == 0
    task = db.scalar(select(TaskRun).where(TaskRun.run_id == "market-context-task"))
    assert task is not None and task.status == "succeeded"
    event = db.scalar(
        select(EventLog)
        .where(EventLog.event_type == "market_context.updated")
        .order_by(EventLog.id.desc())
    )
    assert event is not None
    assert event.payload_json["run_id"] == "market-context-task"
    assert event.payload_json["status"] == "succeeded"
    db.close()
    engine.dispose()


def test_refresh_market_context_task_counts_verified_observation_and_provenance(tmp_path: Path) -> None:
    from app.services.market_context_service import MarketContextService
    from app.services.task_service import TaskService

    engine, db = _context_session()
    config_path = tmp_path / "market-context.json"
    config_path.write_text(
        json.dumps(_verified_context_config().model_dump(mode="json")), encoding="utf-8"
    )
    settings = Settings(_env_file=None, market_context_path=config_path)
    observation = MarketContextObservation.model_validate(
        _observation_payload(context_id="verified-index", source_symbol="INDEX:VERIFIED")
    )
    provider = _ContextCountingProvider(rows=[observation])
    tasks = TaskService(settings)
    tasks.market_context = MarketContextService(provider, settings)
    result = tasks.run(db, "refresh_market_context", run_id="market-context-observed")

    assert result["status"] == "succeeded"
    assert result["configured"] == 1
    assert result["eligible"] == 1
    assert result["observed"] == 1
    assert result["inserted"] == 1
    assert result["missing"] == 0
    assert result["mock"] == 0
    assert result["degraded"] == 0
    assert result["unsupported"] == 0
    assert provider.calls == 1
    db.close()
    engine.dispose()


def test_full_pipeline_market_context_capability_failure_is_partial_without_mock_fallback(tmp_path: Path) -> None:
    from app.models import TaskRun
    from app.services.task_service import TaskService

    config_path = tmp_path / "market-context.json"
    config_path.write_text(
        json.dumps(_verified_context_config().model_dump(mode="json")), encoding="utf-8"
    )
    settings = Settings(_env_file=None, market_context_path=config_path)
    provider = _ContextCountingProvider(error=CapabilityUnavailable("not supported"))
    tasks = TaskService(settings, provider=provider)
    tasks.market.sync_instruments = lambda db, **kwargs: {"created": 0}  # type: ignore[method-assign]
    tasks.market.refresh_daily_bars = lambda db, **kwargs: {"inserted": 0}  # type: ignore[method-assign]
    tasks.indicators.refresh_all = lambda db, **kwargs: {"created": 0}  # type: ignore[method-assign]
    tasks.forecasts.refresh_all = lambda db, **kwargs: {"created": 0}  # type: ignore[method-assign]
    tasks.signals.refresh_all = lambda db, **kwargs: {"created": 0}  # type: ignore[method-assign]

    engine, db = _context_session()
    result = tasks.run(db, "full_pipeline", run_id="market-context-partial", report=False)

    assert result["status"] == "partial"
    assert result["failed_steps"] == ["refresh_market_context"]
    context = result["steps"]["refresh_market_context"]
    assert context["status"] == "failed"
    assert context["unsupported"] == 1
    assert context["observed"] == 0
    assert context["inserted"] == 0
    assert provider.calls == 1
    assert tasks.market_context.latest_view(db)[0]["observation"] is None
    task = db.scalar(select(TaskRun).where(TaskRun.run_id == "market-context-partial"))
    assert task is not None and task.status == "partial"
    db.close()
    engine.dispose()


def test_scheduler_invokes_market_context_as_its_own_due_task(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.scheduler as scheduler

    engine, db = _context_session()
    settings = Settings(_env_file=None, market_context_refresh_minutes=15)
    calls: list[tuple[str, dict]] = []

    class FakeProvider:
        def __init__(self):
            self.close_calls = 0

        def is_trade_day(self, day):
            return True

        def close(self):
            self.close_calls += 1

    class FakeClock:
        def __init__(self, timezone):
            del timezone

        def now(self):
            return datetime(2026, 8, 28, 8, 0, tzinfo=UTC)

        def phase(self, now, is_trade_day):
            del now, is_trade_day
            return scheduler.MarketPhase.PRE_OPEN

        def price_session_open(self, now, is_trade_day):
            del now, is_trade_day
            return False

        def signals_allowed(self, now, is_trade_day):
            del now, is_trade_day
            return False

    class FakeTasks:
        received_provider = None

        def __init__(self, settings, provider=None):
            del settings
            self.provider = provider
            FakeTasks.received_provider = provider

        def close(self):
            return None

        def run(self, db, task_name, **kwargs):
            del db
            calls.append((task_name, kwargs))
            return {"status": "succeeded"}

    @contextmanager
    def fake_session_scope():
        yield db

    monkeypatch.setattr(scheduler, "get_settings", lambda: settings)
    fake_provider = FakeProvider()
    monkeypatch.setattr(scheduler, "create_provider", lambda settings: fake_provider)
    monkeypatch.setattr(scheduler, "MarketClock", FakeClock)
    monkeypatch.setattr(scheduler, "TaskService", FakeTasks)
    monkeypatch.setattr(scheduler, "session_scope", fake_session_scope)
    monkeypatch.setattr(
        scheduler,
        "_last_success",
        lambda db, task_name: None if task_name in {"sync_instruments", "refresh_market_context"} else datetime.now(UTC),
    )

    result = scheduler.tick()

    assert [name for name, _ in calls] == ["sync_instruments", "refresh_market_context"]
    assert result["executed"] == ["sync_instruments", "refresh_market_context"]
    assert FakeTasks.received_provider is fake_provider
    assert fake_provider.close_calls == 1
    db.close()
    engine.dispose()


def test_refresh_market_context_task_failure_retains_sanitized_provider_audit(tmp_path: Path) -> None:
    from app.models import ProviderAudit
    from app.services.task_service import TaskExecutionError, TaskService

    config_path = tmp_path / "market-context.json"
    config_path.write_text(
        json.dumps(_verified_context_config().model_dump(mode="json")), encoding="utf-8"
    )
    settings = Settings(_env_file=None, market_context_path=config_path)
    provider = _ContextCountingProvider(error=CapabilityUnavailable("secret must not persist"))
    engine, db = _context_session()
    tasks = TaskService(settings, provider=provider)

    with pytest.raises(TaskExecutionError):
        tasks.run(db, "refresh_market_context", run_id="market-context-failed")

    audit = db.scalar(
        select(ProviderAudit)
        .where(ProviderAudit.run_id == "market-context-failed")
        .order_by(ProviderAudit.id.desc())
    )
    assert audit is not None
    assert audit.operation == "fetch_market_context"
    assert audit.status == "unsupported"
    assert audit.reason == "CapabilityUnavailable"
    db.close()
    engine.dispose()


def test_market_context_task_counts_only_current_run_observations(tmp_path: Path) -> None:
    from app.services.market_context_service import MarketContextService
    from app.services.task_service import TaskService

    config_path = tmp_path / "market-context.json"
    config_path.write_text(
        json.dumps(_verified_context_config().model_dump(mode="json")), encoding="utf-8"
    )
    settings = Settings(_env_file=None, market_context_path=config_path)
    engine, db = _context_session()
    MarketContextService(MockProvider(), settings).refresh(db, run_id="prior-mock")
    provider = _ContextCountingProvider(rows=[])
    tasks = TaskService(settings, provider=provider)
    result = tasks.run(db, "refresh_market_context", run_id="current-empty")

    assert result["provider_calls"] == 1
    assert result["observed"] == 0
    assert result["missing"] == 1
    assert result["mock"] == 0
    assert result["degraded"] == 0
    assert provider.calls == 1
    db.close()
    engine.dispose()


def test_market_context_pre_provider_validation_failure_reports_zero_calls(tmp_path: Path) -> None:
    from app.services.task_service import TaskService

    item = _verified_context_config().items[0].model_copy(update={"source_priority": ("not-base",)})
    config_path = tmp_path / "market-context.json"
    config_path.write_text(json.dumps(RegistryConfig(items=(item,)).model_dump(mode="json")), encoding="utf-8")
    settings = Settings(_env_file=None, market_context_path=config_path)
    provider = _ContextCountingProvider()
    tasks = TaskService(settings, provider=provider)
    tasks.market.sync_instruments = lambda db, **kwargs: {"created": 0}  # type: ignore[method-assign]
    tasks.market.refresh_daily_bars = lambda db, **kwargs: {"inserted": 0}  # type: ignore[method-assign]
    tasks.indicators.refresh_all = lambda db, **kwargs: {"created": 0}  # type: ignore[method-assign]
    tasks.forecasts.refresh_all = lambda db, **kwargs: {"created": 0}  # type: ignore[method-assign]
    tasks.signals.refresh_all = lambda db, **kwargs: {"created": 0}  # type: ignore[method-assign]
    engine, db = _context_session()

    result = tasks.run(db, "full_pipeline", run_id="pre-provider-failure", report=False)

    assert result["status"] == "partial"
    context = result["steps"]["refresh_market_context"]
    assert context["provider_calls"] == 0
    assert context["unsupported"] == 0
    assert provider.calls == 0
    db.close()
    engine.dispose()


def test_scheduler_context_failure_isolated_and_terminal_attempt_throttles_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.scheduler as scheduler
    from app.services.task_service import TaskExecutionError

    engine, db = _context_session()
    settings = Settings(_env_file=None, market_context_refresh_minutes=15)
    now = datetime(2026, 8, 28, 10, 0, tzinfo=UTC)
    calls: list[str] = []

    class FakeProvider:
        def __init__(self):
            self.close_calls = 0

        def is_trade_day(self, day):
            return True

        def close(self):
            self.close_calls += 1

    class FakeClock:
        def __init__(self, timezone):
            del timezone

        def now(self):
            return now

        def phase(self, at, is_trade_day):
            del at, is_trade_day
            return scheduler.MarketPhase.MORNING

        def price_session_open(self, at, is_trade_day):
            del at, is_trade_day
            return True

        def signals_allowed(self, at, is_trade_day):
            del at, is_trade_day
            return True

    class FakeTasks:
        def __init__(self, settings, provider=None):
            del settings
            self.provider = provider

        def close(self):
            return None

        def run(self, db, task_name, **kwargs):
            del kwargs
            calls.append(task_name)
            db.add(
                TaskRun(
                    run_id=f"{task_name}-{len(calls)}",
                    task_name=task_name,
                    status="failed" if task_name == "refresh_market_context" else "succeeded",
                    started_at=now,
                    finished_at=now,
                    result_json={},
                )
            )
            db.flush()
            if task_name == "refresh_market_context":
                raise TaskExecutionError(f"{task_name}-{len(calls)}", "CapabilityUnavailable")
            return {"status": "succeeded"}

    @contextmanager
    def fake_session_scope():
        yield db

    monkeypatch.setattr(scheduler, "get_settings", lambda: settings)
    providers = []

    def make_provider(settings):
        provider = FakeProvider()
        providers.append(provider)
        return provider

    monkeypatch.setattr(scheduler, "create_provider", make_provider)
    monkeypatch.setattr(scheduler, "MarketClock", FakeClock)
    monkeypatch.setattr(scheduler, "TaskService", FakeTasks)
    monkeypatch.setattr(scheduler, "session_scope", fake_session_scope)

    first = scheduler.tick()
    second = scheduler.tick()

    assert "refresh_market_context" in first["executed"]
    assert [name for name in calls[:5]] == [
        "sync_instruments",
        "refresh_quotes",
        "refresh_market_context",
        "refresh_signals",
        "refresh_news",
    ]
    assert calls.count("refresh_market_context") == 1
    assert "refresh_quotes" not in second["executed"]
    assert all(provider.close_calls == 1 for provider in providers)
    failed = db.scalar(
        select(TaskRun).where(TaskRun.task_name == "refresh_market_context", TaskRun.status == "failed")
    )
    assert failed is not None
    db.close()
    engine.dispose()


class _ImmutableContextProvider(_NoContextProvider):
    """Provider whose fetch method cannot be replaced on an instance."""

    name = "immutable"

    def __init__(self, rows=None, error: Exception | None = None) -> None:
        self.rows = list(rows or [])
        self.error = error

    def __setattr__(self, name, value):
        if name == "fetch_market_context" and hasattr(self, name):
            raise AssertionError("provider method must not be wrapped")
        object.__setattr__(self, name, value)

    def fetch_market_context(self, requests):
        del requests
        if self.error:
            raise self.error
        return list(self.rows)


def test_market_context_service_returns_current_counts_without_mutating_immutable_provider() -> None:
    from app.services.market_context_service import MarketContextService

    engine, db = _context_session()
    observation = MarketContextObservation.model_validate(
        _observation_payload(context_id="verified-index", source_symbol="INDEX:VERIFIED")
    )
    provider = _ImmutableContextProvider(rows=[observation])
    original = provider.fetch_market_context
    service = MarketContextService(provider)

    result = service.refresh(db, config=_verified_context_config(), run_id="immutable-success")

    assert result["provider_calls"] == 1
    assert result["eligible"] == 1
    assert result["observed"] == 1
    assert result["mock"] == 0
    assert result["degraded"] == 0
    assert provider.fetch_market_context == original
    db.close()
    engine.dispose()


def test_market_context_service_failure_outcome_has_actual_call_count_without_mutating_provider() -> None:
    from app.services.market_context_service import MarketContextProviderError, MarketContextService

    engine, db = _context_session()
    provider = _ImmutableContextProvider(error=RuntimeError("private failure"))
    original = provider.fetch_market_context
    with pytest.raises(MarketContextProviderError) as raised:
        MarketContextService(provider).refresh(
            db, config=_verified_context_config(), run_id="immutable-failure"
        )

    outcome = raised.value.outcome
    assert outcome is not None
    assert outcome.provider_calls == 1
    assert outcome.eligible == 1
    assert outcome.observed == 0
    assert outcome.missing == 1
    assert provider.fetch_market_context == original
    db.close()
    engine.dispose()


def test_market_context_pre_provider_failure_outcome_reports_zero_calls() -> None:
    from app.services.market_context_service import MarketContextError, MarketContextService

    engine, db = _context_session()
    item = _verified_context_config().items[0].model_copy(update={"source_priority": ("not-base",)})
    provider = _ImmutableContextProvider()
    original = provider.fetch_market_context
    with pytest.raises(MarketContextError) as raised:
        MarketContextService(provider).refresh(
            db, config=RegistryConfig(items=(item,)), run_id="pre-provider-outcome"
        )

    outcome = raised.value.outcome
    assert outcome is not None
    assert outcome.provider_calls == 0
    assert outcome.observed == 0
    assert provider.fetch_market_context == original
    db.close()
    engine.dispose()


def test_market_context_refresh_persists_mock_observations_idempotently() -> None:
    from app.services.market_context_service import MarketContextService

    engine, db = _context_session()
    config = _verified_context_config()
    provider = MockProvider()
    service = MarketContextService(provider)
    first = service.refresh(db, config=config, run_id="run-one")
    second = service.refresh(db, config=config, run_id="run-two")
    rows = db.scalars(select(MarketContextSnapshot)).all()
    view = service.latest_view(db)

    assert first["requested"] == second["requested"] == 1
    assert first["inserted"] == 1
    assert second["inserted"] == 0
    assert len(rows) == 1
    observation = view[0]["observation"]
    assert observation["source"] == "mock"
    assert observation["is_mock"] is True
    assert observation["verification_status"] == "unverified"
    assert observation["freshness"] == "degraded"
    assert observation["degraded_reason"]
    assert view[0]["status"] == FreshnessStatus.DEGRADED.value
    assert view[0]["verification_status"] == VerificationStatus.VERIFIED.value
    db.close()
    engine.dispose()


def test_market_context_refresh_rejects_unknown_duplicate_and_missing_rows_explicitly() -> None:
    from app.services.market_context_service import MarketContextObservationError, MarketContextService

    engine, db = _context_session()
    config = _verified_context_config()
    source_time = datetime(2026, 8, 28, 9, 30, tzinfo=UTC)
    row = MarketContextObservation(
        context_id="verified-index",
        source_symbol="INDEX:VERIFIED",
        observed_value=1,
        today_pct_change=0.1,
        source="fake",
        source_timestamp=source_time,
        fetched_at=source_time + timedelta(seconds=1),
        freshness=FreshnessStatus.FRESH,
        verification_status=VerificationStatus.VERIFIED,
    )
    provider = _ContextCountingProvider(rows=[])
    service = MarketContextService(provider)
    missing = service.refresh(db, config=config)
    assert missing["missing"] == 1
    assert db.scalars(select(MarketContextSnapshot)).all() == []

    provider.rows = [row.model_copy(update={"context_id": "not-requested"})]
    with pytest.raises(MarketContextObservationError, match="unknown"):
        service.refresh(db, config=config)
    provider.rows = [row, row]
    with pytest.raises(MarketContextObservationError, match="duplicate"):
        service.refresh(db, config=config)
    db.close()
    engine.dispose()


def test_market_context_provider_failure_is_audited_without_raw_exception_or_mock_fallback() -> None:
    from app.models import ProviderAudit
    from app.services.market_context_service import MarketContextProviderError, MarketContextService

    engine, db = _context_session()
    config = _verified_context_config()
    provider = _ContextCountingProvider(error=RuntimeError("private credential must not leak"))
    service = MarketContextService(provider)
    with pytest.raises(MarketContextProviderError, match="RuntimeError"):
        service.refresh(db, config=config, run_id="failed-run")
    audits = db.scalars(select(ProviderAudit)).all()
    assert audits and all("private credential" not in (audit.reason or "") for audit in audits)
    assert db.scalars(select(MarketContextSnapshot)).all() == []
    db.close()
    engine.dispose()


def test_market_context_rejects_source_symbol_mismatch_and_failed_validation_audit() -> None:
    from app.models import ProviderAudit
    from app.services.market_context_service import MarketContextObservationError, MarketContextService

    engine, db = _context_session()
    config = _verified_context_config()
    source_time = datetime(2026, 8, 28, 9, 30, tzinfo=UTC)
    row = MarketContextObservation(
        context_id="verified-index",
        source_symbol="INDEX:WRONG",
        observed_value=1,
        today_pct_change=0.1,
        source="fake",
        source_timestamp=source_time,
        fetched_at=source_time + timedelta(seconds=1),
        freshness=FreshnessStatus.FRESH,
        verification_status=VerificationStatus.VERIFIED,
    )
    provider = CompositeProvider([_ContextCountingProvider(rows=[row])])

    with pytest.raises(MarketContextObservationError, match="source_symbol"):
        MarketContextService(provider).refresh(db, config=config, run_id="invalid-symbol")
    audits = db.scalars(select(ProviderAudit)).all()
    assert audits and all(audit.status == "failed" for audit in audits)
    assert db.scalars(select(MarketContextSnapshot)).all() == []
    db.close()
    engine.dispose()


def test_composite_market_context_preserves_mock_provenance_and_does_not_fabricate_without_mock() -> None:
    from app.services.market_context_service import MarketContextProviderError, MarketContextService

    engine, db = _context_session()
    config = _verified_context_config()
    mock_composite = CompositeProvider([_NoContextProvider(), MockProvider()])
    service = MarketContextService(mock_composite)
    result = service.refresh(db, config=config)
    assert result["inserted"] == 1
    assert service.latest_view(db)[0]["observation"]["is_mock"] is True

    db.close()
    engine.dispose()
    engine, db = _context_session()
    no_mock = CompositeProvider([_NoContextProvider()])
    with pytest.raises(MarketContextProviderError):
        MarketContextService(no_mock).refresh(db, config=config)
    db.close()
    engine.dispose()
