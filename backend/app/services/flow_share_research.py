"""Research view for free ETF flow and exchange share-change fields.

The block sits beside an existing grade. It does not change that grade and it
never sets actionable.
"""

from __future__ import annotations

from typing import Any

FLOW_CONTRACT = "etf-flow-share-v1"
_NOTE = (
    "东财现货资金流、IOPV、折溢价与交易所份额日差只作研究展示。"
    "份额差仅在已验证的相邻交易日标为申赎方向代理。"
    "不改变既有分级，不构成下单。"
)


def build_flow_share_view(quote: Any, scale: Any) -> dict[str, Any]:
    public_quote = quote if quote is not None and not _mockish(getattr(quote, "source", None)) else None
    public_scale = scale if scale is not None and not _mockish(getattr(scale, "source", None)) else None
    blocked = (quote is not None and public_quote is None) or (scale is not None and public_scale is None)
    if public_quote is None and public_scale is None:
        return _empty("mock_blocked" if blocked else "missing")
    payload = _empty("observed")
    if public_quote is not None:
        payload.update(
            {
                "spot_contract": getattr(public_quote, "flow_contract", None),
                "spot_source": getattr(public_quote, "source", None),
                "premium_rate": _number(getattr(public_quote, "premium_rate", None)),
                "iopv": _number(getattr(public_quote, "iopv", None)),
                "latest_shares": _number(getattr(public_quote, "latest_shares", None)),
                "main_net_inflow": _number(getattr(public_quote, "main_net_inflow", None)),
                "super_large_net_inflow": _number(getattr(public_quote, "super_large_net_inflow", None)),
                "large_net_inflow": _number(getattr(public_quote, "large_net_inflow", None)),
                "medium_net_inflow": _number(getattr(public_quote, "medium_net_inflow", None)),
                "small_net_inflow": _number(getattr(public_quote, "small_net_inflow", None)),
            }
        )
    if public_scale is not None:
        trade_date = getattr(public_scale, "trade_date", None)
        previous = getattr(public_scale, "previous_trade_date", None)
        payload["share_scale"] = {
            "status": "observed",
            "proxy": str(getattr(public_scale, "proxy", None) or "不可用"),
            "shares": _number(getattr(public_scale, "shares", None)),
            "previous_shares": _number(getattr(public_scale, "previous_shares", None)),
            "share_delta": _number(getattr(public_scale, "share_delta", None)),
            "share_delta_ratio": _number(getattr(public_scale, "share_delta_ratio", None)),
            "day_over_day": bool(getattr(public_scale, "day_over_day", False)),
            "trade_date": trade_date.isoformat() if hasattr(trade_date, "isoformat") else None,
            "previous_trade_date": previous.isoformat() if hasattr(previous, "isoformat") else None,
            "source": getattr(public_scale, "source", None),
            "exchange": getattr(public_scale, "exchange", None),
            "unit": "shares",
            "actionable": False,
            "research_only": True,
        }
    payload["actionable"] = False
    payload["research_only"] = True
    payload["changes_grade"] = False
    return payload


def _empty(status: str) -> dict[str, Any]:
    return {
        "contract": FLOW_CONTRACT,
        "status": status,
        "research_only": True,
        "actionable": False,
        "changes_grade": False,
        "spot_contract": None,
        "spot_source": None,
        "premium_rate": None,
        "premium_rate_unit": "source_percent",
        "premium_rate_note": "原样保存来源百分比，不由价格和 IOPV 重算，也不反号。",
        "iopv": None,
        "iopv_unit": "cny_per_share",
        "latest_shares": None,
        "latest_shares_unit": "shares",
        "main_net_inflow": None,
        "super_large_net_inflow": None,
        "large_net_inflow": None,
        "medium_net_inflow": None,
        "small_net_inflow": None,
        "net_inflow_unit": "cny",
        "share_scale": {
            "status": "missing" if status == "observed" else status,
            "proxy": "不可用",
            "shares": None,
            "previous_shares": None,
            "share_delta": None,
            "share_delta_ratio": None,
            "day_over_day": False,
            "trade_date": None,
            "previous_trade_date": None,
            "source": None,
            "exchange": None,
            "unit": "shares",
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
    except (TypeError, ValueError):
        return None
    if number != number or number in {float("inf"), float("-inf")}:
        return None
    return number
