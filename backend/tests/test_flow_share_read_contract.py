"""WU2: values have their own source, acquisition cutoff and unit contract."""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from app.providers.share_scale import ALLOWED_SOURCES
from app.services.flow_share_research import build_flow_share_view, saved_flow_share_valid

SHANGHAI = ZoneInfo("Asia/Shanghai")
CUTOFF = datetime(2026, 9, 2, 14, 0, tzinfo=SHANGHAI)


def quote(**changes):
    values = dict(source="akshare:em:v101", flow_contract="etf-spot-flow-v1",
                  quote_time=CUTOFF-timedelta(minutes=1), fetched_at=CUTOFF,
                  timestamp_verified=True, degraded_reason=None, is_realtime=True,
                  premium_rate=-0.4, iopv=4.01, latest_shares=0,
                  main_net_inflow=0, super_large_net_inflow=-10,
                  large_net_inflow=10, medium_net_inflow=None, small_net_inflow=None)
    return SimpleNamespace(**(values | changes))


def scale(**changes):
    values = dict(source="akshare:fund_etf_scale_sse", exchange="SH",
                  trade_date=date(2026, 9, 2), fetched_at=CUTOFF,
                  shares=900, previous_trade_date=date(2026, 9, 1),
                  previous_shares=1000, share_delta=-100, share_delta_ratio=-0.1,
                  day_over_day=True, proxy="份额减少")
    return SimpleNamespace(**(values | changes))


def test_accepted_values_keep_zero_sign_units_and_independent_times():
    value = build_flow_share_view(quote(), scale(), as_of=CUTOFF)
    assert value["contract"] == "etf-flow-share-v2"
    assert value["spot_status"] == "observed"
    assert value["premium_rate"] == -0.4
    assert value["latest_shares"] == value["main_net_inflow"] == 0
    assert value["super_large_net_inflow"] == -10
    assert value["net_inflow_unit"] == "cny"
    assert value["spot_source_time"] == "2026-09-02T13:59:00+08:00"
    assert value["spot_fetched_at"] == value["read_as_of"] == CUTOFF.isoformat()
    assert value["share_scale"]["trade_date"] == "2026-09-02"
    assert value["share_scale"]["fetched_at"] == CUTOFF.isoformat()
    assert value["share_scale"]["share_delta"] == -100
    assert value["share_scale"]["unit"] == "shares"
    assert value["unit_qualification"] == "not_asserted"
    assert "not_historical_pit" in value["view_semantics"]
    assert value["actionable"] is value["changes_grade"] is False
    assert value["research_only"] is True
    assert "is_realtime" not in value


@pytest.mark.parametrize(("changes", "reason"), [
    ({"flow_contract": None}, "flow_contract_unverified"),
    ({"flow_contract": "etf-spot-flow-v99"}, "flow_contract_unverified"),
    ({"source": "tushare:fund_daily:v101"}, "source_not_supported"),
    ({"source": None}, "source_not_supported"),
    ({"source": "mock"}, "mock_blocked"),
    ({"fetched_at": None}, "acquisition_time_unknown"),
    ({"fetched_at": "yesterday"}, "acquisition_time_unknown"),
    ({"fetched_at": CUTOFF+timedelta(microseconds=1)}, "acquisition_after_cutoff"),
    ({"quote_time": CUTOFF+timedelta(microseconds=1)}, "source_after_cutoff"),
    ({"fetched_at": CUTOFF-timedelta(minutes=2)}, "source_after_acquisition"),
])
def test_spot_rejection_does_not_hide_valid_share_evidence(changes, reason):
    value = build_flow_share_view(quote(**changes), scale(), as_of=CUTOFF)
    assert value["spot_status"] == "blocked"
    assert value["spot_reason_code"] == reason
    assert value["main_net_inflow"] is value["premium_rate"] is None
    assert value["share_scale"]["shares"] == 900
    assert value["share_scale"]["status"] == "observed"
    assert value["status"] == "partial"


@pytest.mark.parametrize("changes", [
    {"quote_time": None},
    {"quote_time": "not-a-time"},
    {"degraded_reason": "source_timestamp_missing_observed_at_fetch", "quote_time": CUTOFF},
])
def test_known_acquisition_without_source_time_is_explicitly_unverified(changes):
    value = build_flow_share_view(quote(**changes), None, as_of=CUTOFF)
    assert value["spot_status"] == "degraded"
    assert value["spot_reason_code"] == "source_time_unverified"
    assert value["spot_source_time"] is None
    assert value["spot_fetched_at"] == CUTOFF.isoformat()
    assert value["spot_timestamp_verified"] is False
    assert value["main_net_inflow"] == 0


def test_unverified_source_time_never_inherits_quote_realtime():
    value = build_flow_share_view(quote(timestamp_verified=False), None, as_of=CUTOFF)
    assert value["spot_status"] == "degraded"
    assert value["spot_timestamp_verified"] is False
    assert value["spot_source_time"] == "2026-09-02T13:59:00+08:00"


def test_quote_without_flow_values_is_missing_not_observed():
    q = quote(**{key: None for key in ("premium_rate", "iopv", "latest_shares", "main_net_inflow",
                                     "super_large_net_inflow", "large_net_inflow", "medium_net_inflow", "small_net_inflow")})
    value = build_flow_share_view(q, None, as_of=CUTOFF)
    assert value["spot_status"] == value["status"] == "missing"
    assert value["spot_reason_code"] == "flow_values_missing"


@pytest.mark.parametrize("invalid", [True, float("nan"), float("inf"), float("-inf"), "invalid", 10**1000])
def test_invalid_numbers_remain_null_without_recomputing_other_fields(invalid):
    value = build_flow_share_view(quote(main_net_inflow=invalid, premium_rate=invalid),
                                 scale(share_delta=invalid), as_of=CUTOFF)
    assert value["main_net_inflow"] is value["premium_rate"] is None
    assert value["iopv"] == 4.01
    assert value["share_scale"]["shares"] == 900
    assert value["share_scale"]["share_delta"] is None
    assert value["share_scale"]["proxy"] == "不可用"
    assert value["share_scale"]["day_over_day"] is False


@pytest.mark.parametrize("source", sorted(ALLOWED_SOURCES))
def test_every_existing_exchange_source_keeps_shares_without_conversion(source):
    exchange = "SH" if source.endswith("_sse") else "SZ"
    value = build_flow_share_view(None, scale(source=source, exchange=exchange), as_of=CUTOFF)["share_scale"]
    assert value["status"] == "observed"
    assert value["source"] == source
    assert value["shares"] == 900
    assert value["share_delta"] == -100
    assert value["unit"] == "shares"


@pytest.mark.parametrize(("changes", "reason"), [
    ({"source": "unsupported"}, "source_not_supported"),
    ({"exchange": "SZ"}, "source_exchange_mismatch"),
    ({"exchange": None}, "source_exchange_mismatch"),
    ({"source": "mock"}, "mock_blocked"),
    ({"fetched_at": None}, "acquisition_time_unknown"),
    ({"fetched_at": CUTOFF+timedelta(seconds=1)}, "acquisition_after_cutoff"),
    ({"trade_date": None}, "trade_date_unknown"),
    ({"trade_date": date(2026, 9, 3)}, "trade_date_after_cutoff"),
    ({"fetched_at": CUTOFF-timedelta(days=1)}, "trade_date_after_acquisition"),
    ({"shares": -1}, "share_values_invalid"),
])
def test_share_rejection_does_not_hide_valid_spot_evidence(changes, reason):
    value = build_flow_share_view(quote(), scale(**changes), as_of=CUTOFF)
    assert value["spot_status"] == "observed"
    assert value["main_net_inflow"] == 0
    assert value["share_scale"]["status"] == "blocked"
    assert value["share_scale"]["reason_code"] == reason
    assert value["share_scale"]["shares"] is None
    assert value["share_scale"]["proxy"] == "不可用"


def test_cutoff_compares_instants_and_shanghai_trade_date():
    utc_cutoff = datetime(2026, 9, 1, 16, 0, tzinfo=UTC)
    q = quote(quote_time=utc_cutoff, fetched_at=utc_cutoff)
    s = scale(fetched_at=utc_cutoff)
    a = build_flow_share_view(q, s, as_of=utc_cutoff)
    b = build_flow_share_view(q, s, as_of=utc_cutoff.astimezone(SHANGHAI))
    assert a == b
    assert a["share_scale"]["status"] == "observed"
    assert a["read_as_of"] == "2026-09-02T00:00:00+08:00"


def test_naive_persisted_times_follow_explicit_shanghai_storage_convention():
    value = build_flow_share_view(quote(quote_time=CUTOFF.replace(tzinfo=None),
                                        fetched_at=CUTOFF.replace(tzinfo=None)),
                                 scale(fetched_at=CUTOFF.replace(tzinfo=None)), as_of=CUTOFF)
    assert value["spot_status"] == "observed"
    assert value["spot_source_time"] == CUTOFF.isoformat()
    assert value["spot_time_assumption"] == "naive_storage_asia_shanghai"
    assert value["share_scale"]["time_assumption"] == "naive_storage_asia_shanghai"


def test_naive_cutoff_is_rejected_rather_than_using_process_timezone():
    with pytest.raises(ValueError, match="aware_cutoff_required"):
        build_flow_share_view(quote(), scale(), as_of=CUTOFF.replace(tzinfo=None))


def test_contradictory_delta_cannot_be_a_directional_proxy():
    value = build_flow_share_view(None, scale(shares=900, previous_shares=1000,
                                             share_delta=100, share_delta_ratio=-.1,
                                             proxy="份额增加"), as_of=CUTOFF)["share_scale"]
    assert value["proxy"] == "不可用"
    assert value["day_over_day"] is False
    assert value["reason_code"] == "share_delta_unavailable"


@pytest.mark.parametrize("iopv", [0, -1])
def test_nonpositive_iopv_remains_unknown_like_the_provider_contract(iopv):
    value = build_flow_share_view(quote(iopv=iopv), None, as_of=CUTOFF)
    assert value["iopv"] is None
    assert value["latest_shares"] == value["main_net_inflow"] == 0


@pytest.mark.parametrize("field", ["quote_time", "fetched_at"])
@pytest.mark.parametrize("extreme", [datetime.max.replace(tzinfo=UTC), datetime.min,
                                    datetime.min.replace(tzinfo=SHANGHAI)])
def test_extreme_timestamp_is_blocked_without_overflowing_the_view(field, extreme):
    value = build_flow_share_view(quote(**{field: extreme}), None, as_of=CUTOFF)
    assert value["spot_status"] == "blocked"
    assert value["main_net_inflow"] is None


@pytest.mark.parametrize("state", ["both", "unverified", "blocked", "missing", "mock", "naive", "extreme"])
def test_generated_contract_roundtrips_through_saved_validation(state):
    q, s = quote(), scale()
    if state == "unverified":
        q.quote_time = None
    elif state == "blocked":
        q.fetched_at = None
        s.source = "unsupported"
    elif state == "missing":
        q = s = None
    elif state == "mock":
        q.source = s.source = "mock"
    elif state == "naive":
        q.quote_time = q.quote_time.replace(tzinfo=None)
        q.fetched_at = s.fetched_at = CUTOFF.replace(tzinfo=None)
    elif state == "extreme":
        q.quote_time = datetime.max.replace(tzinfo=UTC)
    value = json.loads(json.dumps(build_flow_share_view(q, s, as_of=CUTOFF)))
    assert saved_flow_share_valid(value, generated_at=CUTOFF.replace(tzinfo=None),
                                 payload_generated_at=CUTOFF.isoformat())
