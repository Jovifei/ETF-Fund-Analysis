"""Deterministic, price-only daily pivots and box research."""
from __future__ import annotations

from datetime import date, datetime
from math import isfinite
from statistics import median
from typing import Any

import numpy as np
import pandas as pd

from app.utils.hashing import stable_hash

ALGORITHM_VERSION = "price-structure-v1"
DEFAULTS = {
    "candidate_window": 120,
    "pivot_window": 2,
    "atr_period": 14,
    "atr_tolerance_multiple": 0.30,
    "minimum_touch_gap": 3,
    "minimum_duration": 20,
    "minimum_inside_ratio": 0.80,
    "minimum_width_atr": 2.0,
    "maximum_width_atr": 12.0,
    "maximum_trend_drift_width": 0.50,
    "expiry_bars": 60,
    "breakout_reversal_bars": 5,
}


def _iso(value: Any) -> str | None:
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.date().isoformat() if isinstance(value, pd.Timestamp) else value.isoformat()[:10]
    try:
        return pd.Timestamp(value).date().isoformat()
    except (TypeError, ValueError):
        return None


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def _normalize(frame: pd.DataFrame) -> tuple[list[dict[str, Any]], str | None]:
    required = {"trade_date", "open", "high", "low", "close"}
    if frame.empty or not required.issubset(frame.columns):
        return [], "price_fields_unavailable"
    by_date: dict[str, dict[str, Any]] = {}
    for row in frame.to_dict("records"):
        day = _iso(row.get("trade_date"))
        values = {key: _number(row.get(key)) for key in ("open", "high", "low", "close")}
        if day is None or any(value is None or value <= 0 for value in values.values()):
            return [], "invalid_ohlc"
        if values["high"] < max(values["open"], values["close"]) or values["low"] > min(values["open"], values["close"]) or values["low"] > values["high"]:
            return [], "invalid_ohlc"
        item = {"trade_date": day, **values, "volume": _number(row.get("volume")), "amount": _number(row.get("amount"))}
        prior = by_date.get(day)
        if prior is not None and prior != item:
            return [], "duplicate_date_conflict"
        by_date[day] = item
    return [by_date[day] for day in sorted(by_date)], None


def _atr_series(rows: list[dict[str, Any]], period: int) -> list[float | None]:
    high = pd.Series([row["high"] for row in rows], dtype=float)
    low = pd.Series([row["low"] for row in rows], dtype=float)
    close = pd.Series([row["close"] for row in rows], dtype=float)
    previous = close.shift(1)
    true_range = pd.concat([(high - low).abs(), (high - previous).abs(), (low - previous).abs()], axis=1).max(axis=1)
    values = true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    return [_number(value) for value in values]


def _prefix_hashes(rows: list[dict[str, Any]], supplied: dict[str, str] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    prior = "0" * 64
    for row in rows:
        day = row["trade_date"]
        prior = (supplied or {}).get(day) or stable_hash({"prior": prior, "row": row})
        result[day] = prior
    return result


def _pivots(rows: list[dict[str, Any]], instrument: str, basis_id: str, window: int,
            prefix_hashes: dict[str, str]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for side, field, is_high in (("high", "high", True), ("low", "low", False)):
        values = [row[field] for row in rows]
        start = 0
        while start < len(values):
            end = start
            while end + 1 < len(values) and values[end + 1] == values[start]:
                end += 1
            confirmed_index = end + window
            if start >= window and confirmed_index < len(values):
                left = values[max(0, start - window):start]
                right = values[end + 1:confirmed_index + 1]
                extreme = max(left) < values[start] and max(right) < values[start] if is_high else min(left) > values[start] and min(right) > values[start]
                if extreme:
                    origin = rows[end]["trade_date"]
                    touch_id = stable_hash({"instrument": instrument, "interval": "1d", "basis": basis_id, "side": side, "origin_at": origin})
                    output.append({"side": side, "price": values[start], "origin_at": origin,
                        "confirmed_at": rows[confirmed_index]["trade_date"], "index": end,
                        "confirmed_index": confirmed_index, "touch_id": touch_id,
                        "input_hash": prefix_hashes[rows[confirmed_index]["trade_date"]]})
            start = end + 1
    return sorted(output, key=lambda item: (item["confirmed_index"], item["side"], item["origin_at"]))


def _clusters(events: list[dict[str, Any]], tolerance: float) -> list[list[dict[str, Any]]]:
    # _normalize guarantees finite positive Python floats. Scalar medians keep
    # the same arithmetic without allocating a NumPy array at every cutoff.
    clusters: list[list[dict[str, Any]]] = []
    for event in sorted(events, key=lambda item: (item["price"], item["origin_at"], item["touch_id"])):
        if not clusters or abs(event["price"] - float(median([item["price"] for item in clusters[-1]]))) > tolerance:
            clusters.append([event])
        else:
            clusters[-1].append(event)
    return clusters


def _separated(events: list[dict[str, Any]], minimum_gap: int) -> list[dict[str, Any]]:
    chosen: list[dict[str, Any]] = []
    for event in sorted(events, key=lambda item: (item["index"], item["touch_id"])):
        if not chosen or event["index"] - chosen[-1]["index"] >= minimum_gap:
            chosen.append(event)
    return chosen


def _drift(closes: list[float]) -> float:
    x = np.arange(len(closes), dtype=float)
    y = np.asarray(closes, dtype=float)
    centered = x - x.mean()
    slope = float((centered * (y - y.mean())).sum() / (centered * centered).sum()) if len(closes) > 1 else 0.0
    return abs(slope * max(0, len(closes) - 1))


def replay_box_lifecycle(
    box: dict[str, Any], rows: list[dict[str, Any]], *, start_index: int,
    pivots: list[dict[str, Any]], tolerance: float, config: dict[str, Any],
    prefix_hashes: dict[str, str], provisional_bar: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Replay settled daily bars; provisional data is returned as a view only."""
    result = dict(box)
    result["state_events"] = [{"date": box["confirmed_at"], "state": "confirmed",
        "reason": "box_conditions_met", "input_hash": prefix_hashes[box["confirmed_at"]]}]
    result["state_events"][0]["event_id"] = stable_hash({"structure_id": box["structure_id"], **result["state_events"][0]})
    result["source_ids"] = list(box["source_ids"])
    known = set(result["source_ids"])
    latest_touch = {"high": max((p["index"] for p in pivots if p["touch_id"] in known and p["side"] == "high"), default=-999),
                    "low": max((p["index"] for p in pivots if p["touch_id"] in known and p["side"] == "low"), default=-999)}
    result["upper_touch_count"] = box["upper_touch_count"]
    result["lower_touch_count"] = box["lower_touch_count"]
    state = "confirmed"
    attempt_side: str | None = None
    attempt_index: int | None = None
    breakout_index: int | None = None
    state_index = start_index
    for index in range(start_index + 1, len(rows)):
        for pivot in pivots:
            if pivot["confirmed_index"] != index or pivot["touch_id"] in known:
                continue
            boundary = result["upper"] if pivot["side"] == "high" else result["lower"]
            if abs(pivot["price"] - boundary) <= tolerance and pivot["index"] - latest_touch[pivot["side"]] >= config["minimum_touch_gap"]:
                known.add(pivot["touch_id"])
                result["source_ids"].append(pivot["touch_id"])
                result["upper_touch_count" if pivot["side"] == "high" else "lower_touch_count"] += 1
                latest_touch[pivot["side"]] = pivot["index"]
        close = rows[index]["close"]
        direction = "upper" if close > result["upper"] + tolerance else "lower" if close < result["lower"] - tolerance else None
        if state == "confirmed" and direction:
            state, attempt_side, attempt_index = "breakout_attempt", direction, index
            event = {"date": rows[index]["trade_date"], "state": state,
                "reason": "settled_close_outside_boundary", "input_hash": prefix_hashes[rows[index]["trade_date"]]}
            event["event_id"] = stable_hash({"structure_id": box["structure_id"], **event})
            result["state_events"].append(event)
        elif state == "breakout_attempt":
            if direction == attempt_side and index == (attempt_index or 0) + 1:
                state, breakout_index = "breakout_confirmed", index
                event = {"date": rows[index]["trade_date"], "state": state,
                    "reason": "two_consecutive_settled_closes", "input_hash": prefix_hashes[rows[index]["trade_date"]]}
                event["event_id"] = stable_hash({"structure_id": box["structure_id"], **event})
                result["state_events"].append(event)
            elif direction is None or direction != attempt_side:
                state = "failed_breakout"
                state_index = index
                event = {"date": rows[index]["trade_date"], "state": state,
                    "reason": "attempt_not_confirmed", "input_hash": prefix_hashes[rows[index]["trade_date"]]}
                event["event_id"] = stable_hash({"structure_id": box["structure_id"], **event})
                result["state_events"].append(event)
        elif state == "breakout_confirmed" and breakout_index is not None and index - breakout_index <= config["breakout_reversal_bars"]:
            opposite = "lower" if attempt_side == "upper" else "upper"
            if direction == opposite:
                state = "invalidated"
                state_index = index
                event = {"date": rows[index]["trade_date"], "state": state,
                    "reason": "close_crossed_opposite_boundary", "input_hash": prefix_hashes[rows[index]["trade_date"]]}
                event["event_id"] = stable_hash({"structure_id": box["structure_id"], **event})
                result["state_events"].append(event)
            elif direction is None:
                state = "failed_breakout"
                state_index = index
                event = {"date": rows[index]["trade_date"], "state": state,
                    "reason": "close_returned_inside_box", "input_hash": prefix_hashes[rows[index]["trade_date"]]}
                event["event_id"] = stable_hash({"structure_id": box["structure_id"], **event})
                result["state_events"].append(event)
        if state in {"failed_breakout", "invalidated"}:
            break
        if index - start_index >= config["expiry_bars"]:
            state = "expired"
            state_index = index
            event = {"date": rows[index]["trade_date"], "state": state,
                "reason": "observation_window_ended", "input_hash": prefix_hashes[rows[index]["trade_date"]]}
            event["event_id"] = stable_hash({"structure_id": box["structure_id"], **event})
            result["state_events"].append(event)
            break
    result["state"] = state
    result["valid_until"] = rows[state_index]["trade_date"] if state in {"failed_breakout", "invalidated", "expired"} else None
    result["source_ids"] = sorted(result["source_ids"])
    result["touch_count"] = result["upper_touch_count"] + result["lower_touch_count"]
    if provisional_bar is not None:
        high, low = _number(provisional_bar.get("high")), _number(provisional_bar.get("low"))
        above = high is not None and high > result["upper"] + tolerance
        below = low is not None and low < result["lower"] - tolerance
        side = "both" if above and below else "upper" if above else "lower" if below else None
        if side:
            result["intraday_state"] = {"state": "breakout_attempt", "side": side,
                "observed_at": _iso(provisional_bar.get("observed_at") or provisional_bar.get("date")),
                "reason": "both_boundaries_crossed" if side == "both" else "provisional_price_outside_box",
                "source_id": stable_hash({"structure_id": result["structure_id"], "bar": provisional_bar})}
    return result


def _first_confirmed_box(rows: list[dict[str, Any]], pivots: list[dict[str, Any]], atrs: list[float | None],
                        settings: dict[str, Any], instrument: str, price_basis_id: str,
                        input_hash: str | None, prefix_hashes: dict[str, str],
                        start_window: int, cursor: int) -> tuple[dict[str, Any] | None, int | None, str]:
    last_failure = "insufficient_independent_touches"
    for end in range(max(20, start_window, cursor), len(rows)):
        atr = atrs[end]
        if atr is None or atr <= 0:
            continue
        tolerance = atr * float(settings["atr_tolerance_multiple"])
        minimum = max(start_window, cursor, end - int(settings["candidate_window"]) + 1)
        known = [p for p in pivots if p["confirmed_index"] <= end and p["index"] >= minimum]
        highs = [_separated(group, int(settings["minimum_touch_gap"])) for group in _clusters([p for p in known if p["side"] == "high"], tolerance)]
        lows = [_separated(group, int(settings["minimum_touch_gap"])) for group in _clusters([p for p in known if p["side"] == "low"], tolerance)]
        choices: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        for upper_events in highs:
            if len(upper_events) < 2:
                continue
            upper = float(median([item["price"] for item in upper_events]))
            for lower_events in lows:
                if len(lower_events) < 2:
                    continue
                lower = float(median([item["price"] for item in lower_events]))
                width = upper - lower
                if width <= 0 or not float(settings["minimum_width_atr"]) <= width / atr <= float(settings["maximum_width_atr"]):
                    last_failure = "box_width_out_of_range"
                    continue
                events = upper_events + lower_events
                indexes = [item["index"] for item in events]
                origin_index = min(indexes)
                if max(indexes) - origin_index < int(settings["minimum_duration"]):
                    last_failure = "box_duration_too_short"
                    continue
                sample = rows[origin_index:end + 1]
                inside = sum(lower - tolerance <= row["close"] <= upper + tolerance for row in sample) / len(sample)
                if inside < float(settings["minimum_inside_ratio"]):
                    last_failure = "box_inside_ratio_too_low"
                    continue
                drift = _drift([row["close"] for row in sample])
                if drift > width * float(settings["maximum_trend_drift_width"]):
                    last_failure = "box_trend_drift_too_high"
                    continue
                source_ids = sorted(item["touch_id"] for item in events)
                structure_id = stable_hash({"algorithm": ALGORITHM_VERSION, "instrument": instrument,
                    "basis": price_basis_id, "origin": rows[origin_index]["trade_date"],
                    "lower": round(lower, 6), "upper": round(upper, 6)})
                candidate = {"kind": "daily_box", "structure_id": structure_id,
                    "lower": round(lower, 6), "upper": round(upper, 6), "mid": round((lower + upper) / 2, 6),
                    "origin_at": rows[origin_index]["trade_date"], "confirmed_at": rows[end]["trade_date"],
                    "valid_from": rows[end]["trade_date"], "valid_until": None, "state": "confirmed",
                    "upper_touch_count": len(upper_events), "lower_touch_count": len(lower_events),
                    "touch_count": len(events), "source_ids": source_ids, "confirmation_tolerance": round(tolerance, 8),
                    "width_atr": round(width / atr, 4), "inside_ratio": round(inside, 4),
                    "trend_drift_width": round(drift / width, 4), "volume_confirmation_available": all(
                        row["volume"] is not None and row["volume"] >= 0 for row in sample),
                    "algorithm_version": ALGORITHM_VERSION, "config_hash": stable_hash(settings),
                    "input_hash": prefix_hashes[rows[end]["trade_date"]], "history_input_hash": input_hash,
                    "price_basis_id": price_basis_id,
                    "interval": "1d", "_upper_events": upper_events, "_lower_events": lower_events}
                choices.append(((-len(events), -inside, structure_id), candidate))
        if choices:
            return min(choices, key=lambda item: item[0])[1], end, last_failure
    return None, None, last_failure


def build_price_structures(
    frame: pd.DataFrame, *, instrument: str, price_basis_id: str,
    config: dict[str, Any] | None = None, expected_dates: list[str] | None = None,
    input_hash: str | None = None, input_hashes_by_date: dict[str, str] | None = None,
    provisional_bar: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = {**DEFAULTS, **(config or {})}
    rows, issue = _normalize(frame)
    result: dict[str, Any] = {"algorithm_version": ALGORITHM_VERSION, "instrument": instrument,
        "interval": "1d", "price_basis_id": price_basis_id, "input_hash": input_hash or stable_hash(rows),
        "config_hash": stable_hash(settings), "qualified": False, "reason": issue,
        "atr14": None, "atr_basis": "wilder_14_from_ohlc", "pivots": [], "boxes": [],
        "candidate": None, "actionable": False, "qualification": "research_only"}
    if issue:
        return result
    if len(rows) < 30:
        result["reason"] = "history_too_short"
        return result
    if expected_dates is not None:
        expected = {_iso(value) for value in expected_dates}
        observed = {row["trade_date"] for row in rows}
        missing = sorted(day for day in expected if day and day not in observed)
        if missing:
            result["reason"] = "trading_day_gap"
            result["missing_dates"] = missing
            return result
        unexpected = sorted(day for day in observed if day not in expected)
        if unexpected:
            result["reason"] = "non_trading_day_bar"
            result["unexpected_dates"] = unexpected
            return result
    atrs = _atr_series(rows, int(settings["atr_period"]))
    result["atr14"] = atrs[-1]
    if atrs[-1] is None or atrs[-1] <= 0:
        result["reason"] = "atr_unavailable"
        return result
    prefix_hashes = _prefix_hashes(rows, input_hashes_by_date)
    pivots = _pivots(rows, instrument, price_basis_id, int(settings["pivot_window"]), prefix_hashes)
    result["pivots"] = [{key: value for key, value in pivot.items() if key not in {"index", "confirmed_index"}} for pivot in pivots]
    result["qualified"] = True
    result["reason"] = None
    start_window = max(0, len(rows) - int(settings["candidate_window"]))
    boxes: list[dict[str, Any]] = []
    cursor = max(20, start_window)
    last_failure = "insufficient_independent_touches"

    # Discover structures at each historical cutoff using the bounded window,
    # then carry confirmed identities forward through the full lifecycle. A
    # later discovery window must not erase a still-live earlier structure.
    discovered: dict[str, tuple[dict[str, Any], int]] = {}
    for cutoff in range(max(30, int(settings["pivot_window"]) * 2 + 1), len(rows) + 1):
        cutoff_rows = rows[:cutoff]
        cutoff_atrs = atrs[:cutoff]
        cutoff_pivots = [pivot for pivot in pivots if pivot["confirmed_index"] < cutoff]
        cutoff_window = max(0, cutoff - int(settings["candidate_window"]))
        cutoff_cursor = max(20, cutoff_window)
        while cutoff_cursor < cutoff:
            found, found_index, last_failure = _first_confirmed_box(
                cutoff_rows, cutoff_pivots, cutoff_atrs, settings, instrument,
                price_basis_id, input_hash, prefix_hashes, cutoff_window, cutoff_cursor
            )
            if found is None or found_index is None:
                break
            structure_id = str(found["structure_id"])
            discovered.setdefault(structure_id, (found, found_index))
            probe = dict(found)
            probe.pop("_upper_events", None)
            probe.pop("_lower_events", None)
            probe = replay_box_lifecycle(
                probe, cutoff_rows, start_index=found_index, pivots=cutoff_pivots,
                tolerance=float(found["confirmation_tolerance"]), config=settings,
                prefix_hashes=prefix_hashes,
            )
            if probe["valid_until"] is None:
                break
            cutoff_cursor = next(
                (index + 1 for index, row in enumerate(cutoff_rows)
                 if row["trade_date"] == probe["valid_until"]),
                cutoff,
            )

    for found, found_index in sorted(discovered.values(), key=lambda item: item[1]):
        found.pop("_upper_events", None)
        found.pop("_lower_events", None)
        box = replay_box_lifecycle(
            found, rows, start_index=found_index, pivots=pivots,
            tolerance=float(found["confirmation_tolerance"]), config=settings,
            prefix_hashes=prefix_hashes, provisional_bar=provisional_bar if not boxes else None,
        )
        box["source_ids"] = sorted(set(box["source_ids"]))
        boxes.append(box)
    result["boxes"] = boxes
    if not boxes and pivots:
        end = len(rows) - 1
        tolerance = float(atrs[end] or 0) * float(settings["atr_tolerance_multiple"])
        minimum = max(start_window, cursor, end - int(settings["candidate_window"]) + 1)
        known = [p for p in pivots if p["confirmed_index"] <= end and p["index"] >= minimum]
        highs = [_separated(group, int(settings["minimum_touch_gap"])) for group in _clusters([p for p in known if p["side"] == "high"], tolerance)]
        lows = [_separated(group, int(settings["minimum_touch_gap"])) for group in _clusters([p for p in known if p["side"] == "low"], tolerance)]
        pairs = [(upper, lower) for upper in highs for lower in lows if len(upper) >= 2 and len(lower) >= 2]
        if pairs:
            upper_events, lower_events = max(pairs, key=lambda pair: (len(pair[0]) + len(pair[1]), -abs(float(median([p["price"] for p in pair[0]])) - float(median([p["price"] for p in pair[1]])))))
            upper, lower = float(median([p["price"] for p in upper_events])), float(median([p["price"] for p in lower_events]))
            events = upper_events + lower_events
            origin = min(p["index"] for p in events)
            structure_id = stable_hash({"algorithm": ALGORITHM_VERSION, "instrument": instrument,
                "basis": price_basis_id, "origin": rows[origin]["trade_date"],
                "lower": round(lower, 6), "upper": round(upper, 6)})
            result["candidate"] = {"state": "candidate", "kind": "daily_box", "structure_id": structure_id,
                "lower": round(lower, 6),
                "upper": round(upper, 6), "mid": round((lower + upper) / 2, 6),
                "origin_at": rows[origin]["trade_date"], "confirmed_at": None,
                "as_of_date": rows[end]["trade_date"], "upper_touch_count": len(upper_events),
                "lower_touch_count": len(lower_events), "touch_count": len(events),
                "source_ids": sorted(p["touch_id"] for p in events),
                "reason": last_failure, "price_basis_id": price_basis_id,
                "input_hash": prefix_hashes[rows[end]["trade_date"]], "history_input_hash": input_hash,
                "algorithm_version": ALGORITHM_VERSION, "config_hash": stable_hash(settings), "interval": "1d"}
        result["reason"] = last_failure if result["candidate"] else "insufficient_independent_touches"
    elif not boxes and not pivots:
        result["reason"] = "no_confirmed_pivots"
    result["volume_confirmation_available"] = all(row["volume"] is not None and row["volume"] >= 0 for row in rows[-int(settings["candidate_window"]):])
    return result
