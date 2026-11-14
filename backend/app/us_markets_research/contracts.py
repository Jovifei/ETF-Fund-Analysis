"""Pandas-free contract for the ``us_markets_research`` display part.

Kept import-light because the local-display bundle validator imports it.
``validate_part`` returns a list of human-readable problems; empty means valid.
Number sanitation (NaN/inf -> None) is the builder's job; here non-finite
numbers are rejected so a bad part can never poison a bundle hash.
"""
from __future__ import annotations

from math import isfinite
from typing import Any

PART_NAME = "us_markets_research"
SCHEMA_VERSION = "us_markets_research_v1"
AVAILABILITY = {"available", "partial", "unavailable"}
SERIES_KINDS = {"basket", "index"}
RISK_BUCKETS = {"low", "mid", "high", "extreme", "unknown"}
RETURN_WINDOWS = ("1w", "1m", "3m", "6m", "ytd", "1y")
MAX_SERIES = 64
MAX_SPARK_POINTS = 400
MAX_PART_TEXT = 2000


def _finite_or_none(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return isfinite(value)


def _scan_numbers(value: Any, path: str, problems: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _scan_numbers(child, f"{path}.{key}", problems)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_numbers(child, f"{path}[{index}]", problems)
    elif isinstance(value, float) and not isfinite(value):
        problems.append(f"{path}: non-finite number")


def validate_series(series: Any, index: int = 0) -> list[str]:
    where = f"series[{index}]"
    if not isinstance(series, dict):
        return [f"{where}: must be an object"]
    problems: list[str] = []
    for key in ("series_id", "label", "group_id"):
        if not isinstance(series.get(key), str) or not series[key]:
            problems.append(f"{where}.{key}: required text")
    if series.get("kind") not in SERIES_KINDS:
        problems.append(f"{where}.kind: must be one of {sorted(SERIES_KINDS)}")
    if series.get("research_only") is not True:
        problems.append(f"{where}.research_only: must be true")
    if series.get("actionable") is not False:
        problems.append(f"{where}.actionable: must be false")
    if series.get("calibration_status") != "not_calibrated":
        problems.append(f"{where}.calibration_status: must be not_calibrated")
    if series.get("available") is False:
        if not isinstance(series.get("reason"), str) or not series["reason"]:
            problems.append(f"{where}.reason: unavailable series must say why")
        return problems
    if series.get("provisional_last_close") is True:
        problems.append(f"{where}.provisional_last_close: prohibited in confirmed metrics")
    for key in ("level", "atr_pct"):
        if not _finite_or_none(series.get(key)):
            problems.append(f"{where}.{key}: finite number or null")
    returns = series.get("returns")
    if not isinstance(returns, dict) or set(returns) - set(RETURN_WINDOWS):
        problems.append(f"{where}.returns: object limited to {RETURN_WINDOWS}")
    elif any(not _finite_or_none(v) for v in returns.values()):
        problems.append(f"{where}.returns: finite number or null")
    if series.get("atr_risk_bucket") not in RISK_BUCKETS:
        problems.append(f"{where}.atr_risk_bucket: unknown bucket")
    spark = series.get("spark")
    if spark is not None and (not isinstance(spark, list) or len(spark) > MAX_SPARK_POINTS
                              or any(not isinstance(p, list) or len(p) != 2 for p in spark)):
        problems.append(f"{where}.spark: list of [date, value] pairs, <= {MAX_SPARK_POINTS}")
    if not isinstance(series.get("as_of"), str):
        problems.append(f"{where}.as_of: required date text")
    return problems


def validate_part(part: Any) -> list[str]:
    """Validate the whole part (the object stored under ``parts['us_markets_research']``)."""
    if not isinstance(part, dict):
        return ["part: must be an object"]
    problems: list[str] = []
    if part.get("price_policy") != "provider_adjusted_daily_OHLC_only; provisional_excluded; no_factor_fill":
        problems.append("price_policy: confirmed adjusted daily observations required")
    if part.get("provisional_closes"):
        problems.append("provisional_closes: must be excluded, not used in metrics")
    if part.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"schema_version: must be {SCHEMA_VERSION}")
    if part.get("research_only") is not True:
        problems.append("research_only: must be true")
    if part.get("actionable") is not False:
        problems.append("actionable: must be false")
    if part.get("changes_grade") is not False:
        problems.append("changes_grade: must be false")
    if part.get("calibration_status") != "not_calibrated":
        problems.append("calibration_status: must be not_calibrated")
    if part.get("availability") not in AVAILABILITY:
        problems.append(f"availability: must be one of {sorted(AVAILABILITY)}")
    if not isinstance(part.get("series"), list):
        problems.append("series: must be a list")
        return problems
    if len(part["series"]) > MAX_SERIES:
        problems.append(f"series: more than {MAX_SERIES} entries")
    if part.get("availability") != "unavailable" and not isinstance(part.get("as_of"), str):
        problems.append("as_of: required unless unavailable")
    if not isinstance(part.get("groups", []), list):
        problems.append("groups: must be a list")
    seen: set[str] = set()
    for index, series in enumerate(part["series"][:MAX_SERIES]):
        problems.extend(validate_series(series, index))
        sid = series.get("series_id") if isinstance(series, dict) else None
        if sid in seen:
            problems.append(f"series[{index}].series_id: duplicate {sid}")
        seen.add(sid)
    _scan_numbers(part, "part", problems)
    return problems
