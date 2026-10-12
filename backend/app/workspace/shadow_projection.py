"""Explicit public daily-chart projection; private/cost overlays never cross sync."""
from datetime import date, datetime, timezone
from math import isfinite
import re
from zoneinfo import ZoneInfo


MARKET_TZ = ZoneInfo("Asia/Shanghai")
INDICATORS = {
    "ma5", "ma10", "ma20", "ma30", "ma60", "macd_dif", "macd_dea", "macd_hist",
    "kdj_k", "kdj_d", "kdj_j", "rsi6", "rsi12", "rsi14", "td_buy_setup",
    "td_sell_setup", "atr", "atr_pct", "boll_upper", "boll_mid", "boll_lower",
}
BAR = {"date", "open", "high", "low", "close", "volume", "amount", "source", "indicators"}
LEVEL = {
    "price", "lower", "upper", "kind", "type", "methods", "groups", "strength",
    "category", "confirmations", "distance_pct", "is_estimate", "touch_count",
}
TREND_LINE = {
    "label", "method", "start_index", "end_index", "start_price", "end_price",
    "projected_price", "slope_per_bar",
}
CHART = {
    "ts_code", "sr_overlay_allowed", "research_sr_overlay_allowed", "basis_transition",
    "adjust", "bars", "research_bars", "available", "source_as_of", "as_of",
    "computed_at", "actionable", "qualification", "research_only", "interval",
    "unsupported_intervals", "indicator_version", "indicator_basis", "input_hash",
    "series_id", "chart_contract_version", "display_price_basis", "research_price_basis",
    "research_price_basis_id", "raw_overlay_allowed", "raw_overlay_reason", "history_issue",
    "reason", "cost_overlay_allowed", "research_cost_overlay_allowed", "studies",
    "support_resistance", "research_support_resistance",
}
STUDY = {
    "levels", "nearest_support", "nearest_resistance", "current_price", "atr14",
    "atr_basis", "reason", "actionable", "qualified", "qualification", "trend_lines",
}
REQUIRED_CHART_FIELDS = {
    "ts_code", "as_of", "source_as_of", "interval", "available", "qualification",
    "research_only", "actionable", "cost_overlay_allowed", "research_cost_overlay_allowed",
    "unsupported_intervals", "bars", "research_bars",
}


def numeric(value, *, nullable=False):
    if value is None and nullable:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError("invalid public numeric field")


def _string(value, *, nullable=False):
    if value is None and nullable:
        return
    if not isinstance(value, str):
        raise ValueError("invalid public string field")


def _iso_date(value, *, nullable=False):
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        raise ValueError("invalid public date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError("invalid public date") from None
    if parsed.isoformat() != value:
        raise ValueError("invalid public date")
    return parsed


def _timestamp(value, field):
    if not isinstance(value, str):
        raise ValueError(f"invalid {field}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"invalid {field}") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"timezone required for {field}")
    return parsed


def _string_list(value, field):
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"invalid public {field}")


def _nonnegative_integer(value, field):
    if type(value) is not int or value < 0:
        raise ValueError(f"invalid public {field}")


def _validate_level(value):
    if not isinstance(value, dict) or set(value) - LEVEL:
        raise ValueError("nonpublic level fields")
    for key in ("price", "lower", "upper", "strength", "distance_pct"):
        if key in value:
            numeric(value[key])
    for key in ("kind", "type", "category"):
        if key in value:
            _string(value[key])
    for key in ("methods", "groups"):
        if key in value:
            _string_list(value[key], key)
    for key in ("confirmations", "touch_count"):
        if key in value:
            _nonnegative_integer(value[key], key)
    if "is_estimate" in value and type(value["is_estimate"]) is not bool:
        raise ValueError("invalid public is_estimate")


def _validate_trend_line(value):
    if not isinstance(value, dict) or set(value) != TREND_LINE:
        raise ValueError("invalid public trend line fields")
    for key in ("label", "method"):
        _string(value[key])
    for key in ("start_index", "end_index"):
        _nonnegative_integer(value[key], key)
    if value["end_index"] <= value["start_index"]:
        raise ValueError("invalid public trend line indices")
    for key in ("start_price", "end_price", "projected_price", "slope_per_bar"):
        numeric(value[key])


def _validate_studies(value):
    if not isinstance(value, dict) or set(value) - STUDY:
        raise ValueError("nonpublic studies")
    for key in ("current_price", "atr14"):
        if key in value:
            numeric(value[key], nullable=key == "atr14")
    for key in ("atr_basis", "reason", "qualification"):
        if key in value:
            _string(value[key], nullable=key in {"atr_basis", "reason"})
    for key in ("actionable", "qualified"):
        if key in value and type(value[key]) is not bool:
            raise ValueError(f"invalid public {key}")
    if value.get("actionable", False) is not False or value.get("qualified", False) is not False:
        raise ValueError("unsafe public studies")
    if "qualification" in value and value["qualification"] != "UNKNOWN":
        raise ValueError("unsafe public study qualification")
    if "levels" in value:
        if not isinstance(value["levels"], list):
            raise ValueError("invalid public levels")
        for item in value["levels"]:
            _validate_level(item)
    for key in ("nearest_support", "nearest_resistance"):
        if key in value and value[key] is not None:
            _validate_level(value[key])
    if "trend_lines" in value:
        if not isinstance(value["trend_lines"], list):
            raise ValueError("invalid public trend lines")
        for item in value["trend_lines"]:
            _validate_trend_line(item)


def levels(value):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("invalid public level")
    return {key: item for key, item in value.items() if key in LEVEL}


def _project_trend_lines(value):
    if not isinstance(value, list):
        raise ValueError("invalid public trend lines")
    projected = []
    for line in value:
        if not isinstance(line, dict):
            raise ValueError("invalid public trend line")
        projected.append({key: item for key, item in line.items() if key in TREND_LINE})
    return projected


def studies(value):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("invalid public studies")
    result = {
        key: item
        for key, item in value.items()
        if key in STUDY and key not in {"levels", "nearest_support", "nearest_resistance", "trend_lines"}
    }
    raw_levels = value.get("levels", [])
    if not isinstance(raw_levels, list):
        raise ValueError("invalid public levels")
    result["levels"] = [levels(item) for item in raw_levels]
    for key in ("nearest_support", "nearest_resistance"):
        result[key] = levels(value.get(key))
    result["trend_lines"] = _project_trend_lines(value.get("trend_lines", []))
    result.update(actionable=False, qualified=False, qualification="UNKNOWN")
    return result


def project_chart(source):
    if not isinstance(source, dict):
        raise ValueError("invalid chart source")
    result = {
        key: value
        for key, value in source.items()
        if key in CHART and key not in {"bars", "research_bars", "studies", "support_resistance", "research_support_resistance"}
    }
    result.setdefault("source_as_of", None)
    for key in ("bars", "research_bars"):
        raw_rows = source.get(key, [])
        if not isinstance(raw_rows, list):
            raise ValueError(f"invalid public {key}")
        result[key] = []
        for row in raw_rows:
            if not isinstance(row, dict):
                raise ValueError(f"invalid public {key} row")
            raw_indicators = row.get("indicators", {})
            if not isinstance(raw_indicators, dict):
                raise ValueError("invalid public indicators")
            bar = {name: item for name, item in row.items() if name in BAR and name != "indicators"}
            bar["indicators"] = {name: item for name, item in raw_indicators.items() if name in INDICATORS}
            result[key].append(bar)
    for key in ("studies", "support_resistance", "research_support_resistance"):
        result[key] = studies(source.get(key))
    result.update(
        interval="1d",
        unsupported_intervals=["1w", "1mo", "5m", "15m"],
        qualification="UNKNOWN",
        research_only=True,
        actionable=False,
        cost_overlay_allowed=False,
        research_cost_overlay_allowed=False,
    )
    return result


def validate_public_chart(chart, *, generated_at=None):
    if not isinstance(chart, dict) or set(chart) - CHART:
        raise ValueError("nonpublic chart fields")
    if REQUIRED_CHART_FIELDS - set(chart):
        raise ValueError("missing public chart fields")
    if not isinstance(chart["ts_code"], str) or not re.fullmatch(r"[0-9]{6}\.(SH|SZ|BJ)", chart["ts_code"]):
        raise ValueError("invalid chart code")
    if chart["interval"] != "1d":
        raise ValueError("chart scope violation")
    if type(chart["available"]) is not bool:
        raise ValueError("invalid public availability")
    if chart["actionable"] is not False or chart["research_only"] is not True or chart["qualification"] != "UNKNOWN":
        raise ValueError("unsafe public chart")
    if chart["cost_overlay_allowed"] is not False or chart["research_cost_overlay_allowed"] is not False:
        raise ValueError("chart scope violation")
    _string(chart["qualification"])
    _string_list(chart["unsupported_intervals"], "unsupported intervals")
    for key in ("sr_overlay_allowed", "research_sr_overlay_allowed", "basis_transition", "raw_overlay_allowed"):
        if key in chart and type(chart[key]) is not bool:
            raise ValueError(f"invalid public {key}")
    for key in ("actionable", "research_only", "cost_overlay_allowed", "research_cost_overlay_allowed"):
        if type(chart[key]) is not bool:
            raise ValueError(f"invalid public {key}")
    for key in (
        "adjust", "indicator_version", "indicator_basis", "input_hash", "series_id",
        "chart_contract_version", "display_price_basis", "research_price_basis",
        "research_price_basis_id", "raw_overlay_reason", "history_issue", "reason",
    ):
        if key in chart:
            _string(chart[key], nullable=True)

    as_of = _timestamp(chart["as_of"], "chart as_of")
    if generated_at is not None:
        if not isinstance(generated_at, datetime) or generated_at.tzinfo is None:
            raise ValueError("invalid bundle generated_at")
        if as_of.astimezone(timezone.utc) > generated_at.astimezone(timezone.utc):
            raise ValueError("chart as_of after bundle generated_at")
    if "computed_at" in chart:
        _timestamp(chart["computed_at"], "chart computed_at")

    source_as_of = _iso_date(chart["source_as_of"], nullable=True)
    market_as_of = as_of.astimezone(MARKET_TZ).date()
    if source_as_of is not None and source_as_of > market_as_of:
        raise ValueError("future chart source date")

    series_dates = {}
    for key in ("bars", "research_bars"):
        rows = chart[key]
        if not isinstance(rows, list):
            raise ValueError(f"invalid public {key}")
        dates = []
        for bar in rows:
            if not isinstance(bar, dict) or set(bar) - BAR:
                raise ValueError("nonpublic bar fields")
            if not isinstance(bar.get("indicators", {}), dict) or set(bar.get("indicators", {})) - INDICATORS:
                raise ValueError("nonpublic indicator fields")
            bar_day = _iso_date(bar.get("date"))
            if bar_day > market_as_of:
                raise ValueError("future chart bar")
            if dates and bar_day <= dates[-1]:
                raise ValueError("duplicate or out-of-order chart dates")
            dates.append(bar_day)
            for field in ("open", "high", "low", "close"):
                numeric(bar.get(field))
            for field in ("volume", "amount"):
                numeric(bar.get(field), nullable=True)
            if bar.get("source") is not None and not isinstance(bar["source"], str):
                raise ValueError("invalid public source")
            for value in bar.get("indicators", {}).values():
                numeric(value, nullable=True)
        series_dates[key] = dates
    if series_dates["bars"] != series_dates["research_bars"]:
        raise ValueError("chart series dates do not match")
    expected_source_as_of = series_dates["bars"][-1] if series_dates["bars"] else None
    if source_as_of != expected_source_as_of:
        raise ValueError("chart source_as_of does not match bars")

    for key in ("studies", "support_resistance", "research_support_resistance"):
        value = chart.get(key)
        if value is not None:
            _validate_studies(value)
