from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import select

from app.core.config import get_settings
from app.models import DailyBar, Instrument
from app.services.backtest_service import RotationBacktestService
from app.services.crosscheck_engine import _filter_bars_from_primary_listing
from app.services.factor_analysis_service import FactorAnalysisService
from app.utils.universe_contract import (
    UNIVERSE_CONTRACT_VERSION,
    current_enabled_universe_contract,
    filter_rows_from_listing,
    parse_listing_date,
)


def test_listing_date_parser_and_current_enabled_contract_are_explicitly_not_survivorship_free():
    assert parse_listing_date("20250106") == date(2025, 1, 6)
    assert parse_listing_date("2025-01-06") == date(2025, 1, 6)
    assert parse_listing_date("") is None
    instruments = [
        SimpleNamespace(ts_code="A.SH", metadata_json={"list_date": "20250106"}),
        SimpleNamespace(ts_code="B.SH", metadata_json={}),
    ]
    contract = current_enabled_universe_contract(instruments)
    assert contract["version"] == UNIVERSE_CONTRACT_VERSION
    assert contract["selection"] == "current_enabled_snapshot"
    assert contract["current_enabled_only"] is True
    assert contract["listing_date_known_count"] == 1
    assert contract["listing_date_coverage"] == 0.5
    assert contract["historical_membership_available"] is False
    assert contract["delist_history_available"] is False
    assert contract["survivorship_bias_controlled"] is False
    assert contract["qualification"] == "UNKNOWN"


def test_listing_filter_removes_only_prelisting_rows():
    inst = SimpleNamespace(metadata_json={"list_date": "20250106"})
    rows = [
        SimpleNamespace(trade_date=date(2025, 1, 3)),
        SimpleNamespace(trade_date=date(2025, 1, 6)),
        SimpleNamespace(trade_date=date(2025, 1, 7)),
    ]
    kept, evidence = filter_rows_from_listing(rows, inst)
    assert [row.trade_date for row in kept] == [date(2025, 1, 6), date(2025, 1, 7)]
    assert evidence["list_date"] == "2025-01-06"
    assert evidence["listing_date_known"] is True
    assert evidence["prelisting_rows_removed"] == 1


def _unique_code(db_session, prefix: str) -> str:
    occupied = set(
        db_session.scalars(
            select(Instrument.ts_code).where(Instrument.ts_code.like(f"{prefix}%.SH"))
        ).all()
    )
    start = int(prefix) * 10 ** (6 - len(prefix))
    stop = (int(prefix) + 1) * 10 ** (6 - len(prefix))
    code = next(
        (f"{value:06d}.SH" for value in range(start, stop) if f"{value:06d}.SH" not in occupied),
        None,
    )
    assert code is not None
    return code


def _seed(db_session, *, code: str, listing: date, rows: int = 210) -> Instrument:
    inst = Instrument(
        ts_code=code,
        symbol=code[:6],
        name=uuid4().hex,
        kind="ETF",
        enabled=True,
        metadata_json={"list_date": listing.strftime("%Y%m%d"), "catalog_source": "fixture"},
    )
    db_session.add(inst)
    db_session.flush()
    start = listing - timedelta(days=25)
    for idx in range(rows):
        day = start + timedelta(days=idx)
        price = 1.0 + idx * 0.001
        db_session.add(
            DailyBar(
                instrument_id=inst.id,
                trade_date=day,
                open=price,
                high=price + 0.01,
                low=price - 0.01,
                close=price,
                volume=1000.0,
                amount=1000.0 * price,
                source="akshare:em:v101",
                adjust="none",
                quality_hash=f"{code}-{idx}",
            )
        )
    db_session.flush()
    return inst


def test_factor_panel_filters_prelisting_rows_and_carries_universe_contract(db_session):
    listing = date(2025, 2, 1)
    code = _unique_code(db_session, "96")
    inst = _seed(db_session, code=code, listing=listing)
    settings = get_settings().model_copy(update={"market_provider": "akshare"})
    panel = FactorAnalysisService(settings)._panel(db_session, instrument_ids={inst.id})
    assert not panel.empty
    assert panel["trade_date"].min() >= listing
    research = panel.attrs["research_input_contract"]["basis_by_instrument"][code]
    assert research["listing_date_known"] is True
    assert research["prelisting_rows_removed"] > 0
    universe = panel.attrs["universe_contract"]
    classification = panel.attrs["classification_contract"]
    assert universe["version"] == UNIVERSE_CONTRACT_VERSION
    assert universe["listing_dates"][code] == listing.isoformat()
    assert universe["survivorship_bias_controlled"] is False
    assert classification["theme_point_in_time_qualified"] is False
    db_session.rollback()


def test_transaction_backtest_filters_prelisting_rows_but_does_not_claim_historical_membership(db_session):
    listing = date(2025, 2, 1)
    code = _unique_code(db_session, "95")
    _seed(db_session, code=code, listing=listing, rows=60)
    settings = get_settings().model_copy(update={"market_provider": "akshare"})
    _, frames, exclusions, universe, classification = RotationBacktestService(settings)._load_frames(db_session)
    assert code not in {item["ts_code"] for item in exclusions}
    assert frames[code].index.min() >= listing
    assert universe["listing_dates"][code] == listing.isoformat()
    assert universe["historical_membership_available"] is False
    assert universe["survivorship_bias_controlled"] is False
    assert classification["theme_point_in_time_qualified"] is False
    assert classification["historical_projection_policy"] == "diagnostic_only_current_labels_projected_over_history"
    db_session.rollback()


def test_crosscheck_replay_uses_primary_listing_evidence_not_current_metadata():
    bars = [
        SimpleNamespace(trade_date=date(2025, 1, 3)),
        SimpleNamespace(trade_date=date(2025, 1, 6)),
        SimpleNamespace(trade_date=date(2025, 1, 7)),
    ]
    primary_contract = {
        "version": UNIVERSE_CONTRACT_VERSION,
        "listing_dates": {"TEST.SH": "2025-01-06"},
    }
    kept = _filter_bars_from_primary_listing(bars, "TEST.SH", primary_contract)
    assert [bar.trade_date for bar in kept] == [date(2025, 1, 6), date(2025, 1, 7)]

    # Current Instrument metadata is intentionally absent from this helper:
    # the replay is pinned to primary-report evidence, not today's catalog.
    assert _filter_bars_from_primary_listing(bars, "OTHER.SH", primary_contract) == bars
