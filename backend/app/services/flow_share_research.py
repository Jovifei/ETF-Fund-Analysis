"""Research view for free ETF flow and exchange share-change fields.

The block sits beside an existing grade. It does not change that grade and it
never sets actionable.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EtfShareScale
from app.providers.akshare import SPOT_FLOW_CONTRACT
from app.providers.share_scale import ALLOWED_SOURCES

FLOW_CONTRACT = "etf-flow-share-v2"
SHANGHAI = ZoneInfo("Asia/Shanghai")
_SPOT_FIELDS = ("premium_rate", "iopv", "latest_shares", "main_net_inflow",
                "super_large_net_inflow", "large_net_inflow", "medium_net_inflow", "small_net_inflow")
_NOTE = (
    "东财现货资金流、IOPV、折溢价与交易所份额日差只作研究展示。"
    "份额差仅在已验证的相邻交易日标为申赎方向代理。"
    "不改变既有分级，不构成下单。"
)


def build_flow_share_view(quote: Any, scale: Any, *, as_of: datetime) -> dict[str, Any]:
    """Read current persisted evidence known by cutoff, never reconstruct PIT."""
    cutoff = _cutoff(as_of)
    payload = _empty("missing")
    payload["read_as_of"] = cutoff.isoformat()
    if quote is not None:
        _spot(payload, quote, cutoff)
    if scale is not None:
        _scale(payload["share_scale"], scale, cutoff)
    payload["status"] = _view_status(payload)
    return payload


def _view_status(payload: dict[str, Any]) -> str:
    states = (payload["spot_status"], payload["share_scale"]["status"])
    if states == ("observed", "observed"):
        return "observed"
    if any(state in {"observed", "degraded"} for state in states):
        return "partial"
    if "blocked" in states:
        reasons = (payload["spot_reason_code"], payload["share_scale"]["reason_code"])
        return "mock_blocked" if "mock_blocked" in reasons else "blocked"
    return "missing"


def latest_share_scales(db: Session, *, as_of: datetime, instrument_ids: list[int] | None = None) -> dict[int, EtfShareScale]:
    """Newest known record, including totals without a delta; no historical repair."""
    cutoff = _cutoff(as_of)
    query = select(EtfShareScale).where(EtfShareScale.trade_date <= cutoff.date())
    if instrument_ids is not None:
        query = query.where(EtfShareScale.instrument_id.in_(instrument_ids))
    rows = db.scalars(query.order_by(EtfShareScale.trade_date.desc(), EtfShareScale.id.desc())).all()
    result: dict[int, EtfShareScale] = {}
    for row in rows:
        fetched, _ = _time(row.fetched_at)
        if fetched is not None and fetched.astimezone(UTC) <= cutoff.astimezone(UTC):
            result.setdefault(row.instrument_id, row)
    return result


def blocked_flow_share_view(original: Any, *, board_version: Any, reason: str) -> dict[str, Any]:
    """An explicit read projection, never a relabelled or rewritten old snapshot."""
    original_contract = original.get("contract") if isinstance(original, dict) else None
    value = _empty("blocked")
    value.update(contract=original_contract, original_contract=original_contract,
                 original_board_version=board_version, projection_kind="blocked_saved_contract",
                 spot_status="blocked", spot_reason_code=reason)
    value["share_scale"].update(status="blocked", reason_code=reason)
    return value


def saved_flow_share_valid(value: Any, *, generated_at: datetime, payload_generated_at: Any) -> bool:
    """Validate the saved projection only; no DB hydration or research calculation.

    Reapply admission to its recorded fields, not to newer source rows. Numeric
    values are neither recalculated nor repaired. Unknown/extra schema fails
    closed, and the record cannot move its cutoff beyond its containing board.
    """
    if not isinstance(value, dict) or value.get("contract") != FLOW_CONTRACT:
        return False
    if value.get("actionable") is not False or value.get("changes_grade") is not False or value.get("research_only") is not True:
        return False
    scale = value.get("share_scale")
    if not isinstance(scale, dict) or scale.get("actionable") is not False or scale.get("research_only") is not True:
        return False
    try:
        cutoff, _ = _time(generated_at)
        if cutoff is None or _saved_time(value["read_as_of"]) != cutoff or _saved_time(payload_generated_at) != cutoff:
            return False
        if not isinstance(value["spot_timestamp_verified"], bool) or not isinstance(scale["day_over_day"], bool):
            return False
        spot = None if value["spot_reason_code"] == "spot_missing" else SimpleNamespace(
            source=value["spot_source"], flow_contract=value["spot_contract"],
            quote_time=_saved_time(value["spot_source_time"]), fetched_at=_saved_time(value["spot_fetched_at"]),
            timestamp_verified=value["spot_timestamp_verified"], **{key: value[key] for key in _SPOT_FIELDS},
        )
        shares = None if scale["reason_code"] == "share_scale_missing" else SimpleNamespace(
            **{key: scale[key] for key in ("source", "exchange", "shares", "previous_shares", "share_delta",
                                          "share_delta_ratio", "day_over_day", "proxy")},
            fetched_at=_saved_time(scale["fetched_at"]),
            trade_date=date.fromisoformat(scale["trade_date"]) if scale["trade_date"] is not None else None,
            previous_trade_date=date.fromisoformat(scale["previous_trade_date"]) if scale["previous_trade_date"] is not None else None,
        )
        expected = build_flow_share_view(spot, shares, as_of=cutoff)
        if value["spot_reason_code"] == "source_time_invalid":
            # Failed normalization intentionally stores no malformed timestamp
            # or numbers. This empty, blocked component must not erase a valid
            # independent share component when its saved view is read again.
            if (value["spot_source_time"] is not None or any(value[key] is not None for key in _SPOT_FIELDS)
                    or expected["spot_reason_code"] != "flow_values_missing"):
                return False
            expected.update(spot_status="blocked", spot_reason_code="source_time_invalid",
                            premium_rate_unit=None, iopv_unit=None, latest_shares_unit=None, net_inflow_unit=None)
            expected["status"] = _view_status(expected)
        # Serialized timestamps are aware; retain only the declared storage
        # convention rather than silently erasing a known SQLite assumption.
        for actual, target, key in ((value, expected, "spot_time_assumption"),
                                    (scale, expected["share_scale"], "time_assumption")):
            if actual[key] not in (None, "naive_storage_asia_shanghai"):
                return False
            target[key] = actual[key]
        return expected == value
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def _saved_time(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("saved_timestamp_invalid")
    return _cutoff(datetime.fromisoformat(value))


def _spot(payload: dict[str, Any], quote: Any, cutoff: datetime) -> None:
    source, contract = getattr(quote, "source", None), getattr(quote, "flow_contract", None)
    fetched, naive_fetch = _time(getattr(quote, "fetched_at", None))
    raw_source_time = getattr(quote, "quote_time", None)
    source_time, naive_source = _time(raw_source_time)
    invalid_source_time = isinstance(raw_source_time, datetime) and source_time is None
    if str(getattr(quote, "degraded_reason", "") or "").startswith("source_timestamp_missing"):
        source_time = None
        invalid_source_time = False
    payload.update(spot_source=source, spot_contract=contract,
                   spot_source_time=source_time.isoformat() if source_time else None,
                   spot_fetched_at=fetched.isoformat() if fetched else None,
                   spot_time_assumption="naive_storage_asia_shanghai" if naive_fetch or naive_source else None)
    reason = "mock_blocked" if _mockish(source) else "source_not_supported" if source != "akshare:em:v101" else None
    if reason is None and contract != SPOT_FLOW_CONTRACT:
        reason = "flow_contract_unverified"
    if reason is None:
        reason = _acquisition_reason(fetched, cutoff)
    if reason is None and invalid_source_time:
        reason = "source_time_invalid"
    if reason is None and source_time is not None and source_time.astimezone(UTC) > cutoff.astimezone(UTC):
        reason = "source_after_cutoff"
    if reason is None and source_time is not None and source_time.astimezone(UTC) > fetched.astimezone(UTC):
        reason = "source_after_acquisition"
    if reason:
        payload.update(spot_status="blocked", spot_reason_code=reason)
        return
    payload.update({key: _number(getattr(quote, key, None)) for key in _SPOT_FIELDS})
    if payload["latest_shares"] is not None and payload["latest_shares"] < 0:
        payload["latest_shares"] = None
    if payload["iopv"] is not None and payload["iopv"] <= 0:
        payload["iopv"] = None
    payload.update(premium_rate_unit="source_percent", iopv_unit="cny_per_share",
                   latest_shares_unit="shares", net_inflow_unit="cny")
    if not any(payload[key] is not None for key in _SPOT_FIELDS):
        payload.update(spot_status="missing", spot_reason_code="flow_values_missing")
        return
    verified = source_time is not None and getattr(quote, "timestamp_verified", False) is True
    payload.update(spot_status="observed" if verified else "degraded",
                   spot_reason_code=None if verified else "source_time_unverified",
                   spot_timestamp_verified=verified)


def _scale(value: dict[str, Any], scale: Any, cutoff: datetime) -> None:
    source = getattr(scale, "source", None)
    fetched, naive = _time(getattr(scale, "fetched_at", None))
    trade_date = getattr(scale, "trade_date", None)
    if not isinstance(trade_date, date) or isinstance(trade_date, datetime):
        trade_date = None
    value.update(source=source, exchange=getattr(scale, "exchange", None),
                 trade_date=trade_date.isoformat() if trade_date else None,
                 fetched_at=fetched.isoformat() if fetched else None,
                 time_assumption="naive_storage_asia_shanghai" if naive else None)
    reason = "mock_blocked" if _mockish(source) else "source_not_supported" if not isinstance(source, str) or source not in ALLOWED_SOURCES else None
    if reason is None and value["exchange"] != ("SH" if source.endswith("_sse") else "SZ"):
        reason = "source_exchange_mismatch"
    if reason is None:
        reason = _acquisition_reason(fetched, cutoff)
    if reason is None and trade_date is None:
        reason = "trade_date_unknown"
    if reason is None and trade_date > cutoff.date():
        reason = "trade_date_after_cutoff"
    if reason is None and trade_date > fetched.date():
        reason = "trade_date_after_acquisition"
    shares = _number(getattr(scale, "shares", None))
    if reason is None and (shares is None or shares < 0):
        reason = "share_values_invalid"
    if reason:
        value.update(status="blocked", reason_code=reason)
        return
    previous = getattr(scale, "previous_trade_date", None)
    if not isinstance(previous, date) or isinstance(previous, datetime):
        previous = None
    prior_shares = _number(getattr(scale, "previous_shares", None))
    delta = _number(getattr(scale, "share_delta", None))
    ratio = _number(getattr(scale, "share_delta_ratio", None))
    proxy = getattr(scale, "proxy", None)
    valid_proxy = (getattr(scale, "day_over_day", False) is True and previous is not None
                   and previous < trade_date and prior_shares is not None and prior_shares > 0
                   and delta is not None and ratio is not None
                   and ((shares > prior_shares and delta > 0 and ratio > 0 and proxy == "份额增加")
                        or (shares < prior_shares and delta < 0 and ratio < 0 and proxy == "份额减少")
                        or (shares == prior_shares and delta == 0 and ratio == 0 and proxy == "份额不变")))
    value.update(status="observed", reason_code=None if valid_proxy else "share_delta_unavailable",
                 shares=shares, previous_shares=prior_shares, share_delta=delta, share_delta_ratio=ratio,
                 previous_trade_date=previous.isoformat() if previous else None,
                 day_over_day=valid_proxy, proxy=proxy if valid_proxy else "不可用", unit="shares")


def _cutoff(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("aware_cutoff_required")
    return value.astimezone(SHANGHAI)


def _time(value: Any) -> tuple[datetime | None, bool]:
    # Repository/SQLite storage convention, explicitly exposed in the view.
    if not isinstance(value, datetime):
        return None, False
    try:
        naive = value.tzinfo is None or value.utcoffset() is None
        normalized = value.replace(tzinfo=SHANGHAI) if naive else value.astimezone(SHANGHAI)
        normalized.astimezone(UTC)  # Establish both comparison/display conversions safely.
        return normalized, naive
    except (ValueError, OverflowError):
        return None, False


def _acquisition_reason(fetched: datetime | None, cutoff: datetime) -> str | None:
    if fetched is None:
        return "acquisition_time_unknown"
    return "acquisition_after_cutoff" if fetched.astimezone(UTC) > cutoff.astimezone(UTC) else None


def _empty(status: str) -> dict[str, Any]:
    return {
        "contract": FLOW_CONTRACT,
        "projection_contract": FLOW_CONTRACT,
        "projection_kind": "current_persisted_evidence",
        "view_semantics": "current_persisted_evidence_bounded_by_observation_time_not_historical_pit",
        "unit_qualification": "not_asserted",
        "read_as_of": None,
        "status": status,
        "research_only": True,
        "actionable": False,
        "changes_grade": False,
        "spot_contract": None,
        "spot_source": None,
        "spot_status": "missing",
        "spot_reason_code": "spot_missing",
        "spot_source_time": None,
        "spot_fetched_at": None,
        "spot_timestamp_verified": False,
        "spot_time_assumption": None,
        "premium_rate": None,
        "premium_rate_unit": None,
        "premium_rate_note": "原样保存来源百分比，不由价格和 IOPV 重算，也不反号。",
        "iopv": None,
        "iopv_unit": None,
        "latest_shares": None,
        "latest_shares_unit": None,
        "main_net_inflow": None,
        "super_large_net_inflow": None,
        "large_net_inflow": None,
        "medium_net_inflow": None,
        "small_net_inflow": None,
        "net_inflow_unit": None,
        "share_scale": {
            "status": "missing",
            "reason_code": "share_scale_missing",
            "proxy": "不可用",
            "shares": None,
            "previous_shares": None,
            "share_delta": None,
            "share_delta_ratio": None,
            "day_over_day": False,
            "trade_date": None,
            "previous_trade_date": None,
            "fetched_at": None,
            "time_assumption": None,
            "source": None,
            "exchange": None,
            "unit": None,
            "actionable": False,
            "research_only": True,
        },
        "note": _NOTE,
    }


def _mockish(source: object) -> bool:
    return "mock" in str(source or "").lower()


def _number(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if number != number or number in {float("inf"), float("-inf")}:
        return None
    return number
