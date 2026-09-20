"""Absolute 量/额 units: independent cross-check certifies; ratio never does."""
from datetime import date, datetime
from types import SimpleNamespace

from app.core.config import get_settings
from app.providers.akshare import AKShareProvider
from app.providers.unit_certification import (
    UnitObservation,
    certify_absolute_units,
    history_units_independently_certified,
)
from app.services.qualification_gate import qualify_1430
from app.services.etf_1430_service import ETF1430WorkbenchService


def _obs(**kwargs):
    payload = dict(
        ts_code="510300.SH",
        trade_date=date(2026, 9, 11),
        close=1.2,
        source="tushare:fund_daily:v101",
        raw_volume=20.0,
        raw_amount=2.4,
        converted_volume=2000.0,
        converted_amount=2400.0,
    )
    payload.update(kwargs)
    return UnitObservation(**payload)


def test_documented_same_day_second_source_certifies_absolute_units():
    primary = _obs()
    independent = _obs(
        source="akshare:em:v101",
        raw_volume=20.0,
        raw_amount=2400.0,
        converted_volume=2000.0,
        converted_amount=2400.0,
    )
    result = certify_absolute_units(primary, independent)
    assert result.certified is True
    assert result.volume == 2000.0
    assert result.amount == 2400.0
    assert result.ratio_sanity_passed is True
    assert "ratio_only" not in " ".join(result.reasons)


def test_sina_observed_share_units_can_certify_against_tencent():
    primary = _obs(
        source="tencent:stock_zh_a_hist_tx:v101",
        raw_volume=2000.0,
        raw_amount=2400.0,
        converted_volume=2000.0,
        converted_amount=2400.0,
    )
    independent = _obs(
        source="akshare:sina:v101",
        raw_volume=2000.0,
        raw_amount=2400.0,
        converted_volume=None,
        converted_amount=None,
    )

    result = certify_absolute_units(primary, independent)

    assert result.certified is True


def test_large_public_source_rounding_stays_within_relative_tolerance():
    primary = _obs(
        source="tencent:stock_zh_a_hist_tx:v101",
        close=1.325,
        raw_volume=143_640_700.0,
        raw_amount=189_828_800.0,
        converted_volume=143_640_700.0,
        converted_amount=189_828_800.0,
    )
    independent = _obs(
        source="akshare:sina:v101",
        close=1.325,
        raw_volume=143_640_727.0,
        raw_amount=189_828_818.0,
        converted_volume=None,
        converted_amount=None,
    )

    result = certify_absolute_units(primary, independent)

    assert result.certified is True


def test_ratio_only_same_vwap_is_sanity_never_qualification():
    primary = _obs()
    # Simultaneous ×100 keeps amount/volume = close, so VWAP still matches.
    independent = _obs(
        source="akshare:em:v101",
        raw_volume=2000.0,
        raw_amount=240000.0,
        converted_volume=200000.0,
        converted_amount=240000.0,
    )
    result = certify_absolute_units(primary, independent)
    assert result.certified is False
    assert result.ratio_sanity_passed is True
    assert "absolute_volume_mismatch" in result.reasons
    assert "ratio_only_is_not_qualification" in result.reasons


def test_unknown_endpoint_fails_closed_even_when_numbers_look_canonical():
    result = certify_absolute_units(
        _obs(source="mystery:undocumented"),
        _obs(source="akshare:em:v101", raw_volume=20.0, raw_amount=2400.0),
    )
    assert result.certified is False
    assert "unknown_endpoint_units_unverified" in result.reasons


def test_mismatched_independent_observation_fails_closed():
    result = certify_absolute_units(
        _obs(),
        _obs(
            source="akshare:em:v101",
            raw_volume=21.0,
            raw_amount=2520.0,
            converted_volume=2100.0,
            converted_amount=2520.0,
        ),
    )
    assert result.certified is False
    assert "absolute_volume_mismatch" in result.reasons


def test_missing_volume_and_amount_stay_missing_never_zero_for_scoring():
    sina_volume, sina_amount, sina_source = AKShareProvider._sina_volume_fields(1.2, 1000, 1200)
    assert sina_volume is None and sina_amount is None
    assert sina_source == "akshare:sina:v101"

    result = certify_absolute_units(
        _obs(
            source="akshare:sina:v101",
            raw_volume=None,
            raw_amount=None,
            converted_volume=None,
            converted_amount=None,
        ),
        _obs(source="akshare:em:v101", raw_volume=20.0, raw_amount=2400.0),
    )
    assert result.certified is False
    assert result.volume is None
    assert result.amount is None
    assert result.volume != 0 and result.amount != 0
    assert "volume_or_amount_missing" in result.reasons
    assert "sina_absolute_units_unverified" in result.reasons


def test_price_only_history_rows_are_not_independently_certified():
    rows = [
        SimpleNamespace(
            trade_date=date(2026, 9, 11),
            open=1.2,
            high=1.21,
            low=1.19,
            close=1.2,
            volume=None,
            amount=None,
            source="akshare:sina:v101",
            adjust="none",
        )
    ]
    status = history_units_independently_certified(rows)
    assert status.certified is False
    assert status.volume is None
    assert "independent_same_day_observation_missing" in status.reasons


def test_qualify_1430_blocks_uncertified_units_and_stays_not_actionable():
    settings = get_settings().model_copy(update={"market_provider": "akshare"})
    now = datetime(2026, 8, 31, 14, 30, tzinfo=settings.timezone)
    quote = SimpleNamespace(
        source="fixture:realtime",
        price=1.2,
        quote_time=now,
        is_realtime=True,
        timestamp_verified=True,
        degraded_reason=None,
    )
    bars = [
        SimpleNamespace(
            trade_date=date(2026, 8, 28),
            open=1.2,
            high=1.21,
            low=1.19,
            close=1.2,
            volume=2000,
            amount=2400,
            source="akshare:em:v101",
            adjust="none",
        )
    ]
    result = qualify_1430(
        settings,
        quote,
        now,
        {"inside": True, "maximum_quote_age_minutes": 8},
        bars=bars,
    )
    assert result["actionable"] is False
    assert "absolute_units_not_independently_certified" in result["reasons"]
    assert "historical_1430_backtest_not_qualified" in result["reasons"]


def test_certified_fixture_still_cannot_flip_1430_actionable():
    settings = get_settings().model_copy(update={"market_provider": "akshare"})
    now = datetime(2026, 8, 31, 14, 30, tzinfo=settings.timezone)
    quote = SimpleNamespace(
        source="fixture:realtime",
        price=1.2,
        quote_time=now,
        is_realtime=True,
        timestamp_verified=True,
        degraded_reason=None,
    )
    certified = certify_absolute_units(
        _obs(),
        _obs(source="akshare:em:v101", raw_volume=20.0, raw_amount=2400.0,
             converted_volume=2000.0, converted_amount=2400.0),
    )
    assert certified.certified is True
    result = qualify_1430(
        settings,
        quote,
        now,
        {"inside": True, "maximum_quote_age_minutes": 8},
        unit_certification=certified,
    )
    assert "absolute_units_not_independently_certified" not in result["reasons"]
    assert result["actionable"] is False
    assert "historical_1430_backtest_not_qualified" in result["reasons"]


def test_workbench_passes_explicit_independent_unit_certification_to_gate():
    settings = get_settings().model_copy(update={"market_provider": "akshare"})
    now = datetime(2026, 8, 31, 14, 30, tzinfo=settings.timezone)
    quote = SimpleNamespace(
        source="fixture:realtime",
        price=1.2,
        quote_time=now,
        is_realtime=True,
        timestamp_verified=True,
        degraded_reason=None,
    )
    certified = certify_absolute_units(
        _obs(),
        _obs(
            source="akshare:em:v101",
            raw_volume=20.0,
            raw_amount=2400.0,
            converted_volume=2000.0,
            converted_amount=2400.0,
        ),
    )
    result = ETF1430WorkbenchService(
        settings,
        unit_certification_resolver=lambda bars: certified,
    )._qualification(
        quote,
        now,
        bars=[],
        indicator=None,
    )
    assert "absolute_units_not_independently_certified" not in result["reasons"]
    assert result["actionable"] is False
