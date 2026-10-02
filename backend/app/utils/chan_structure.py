"""Simplified Chan research geometry from OHLC.

``chanlun`` is an optional market extra and the stabilization board only counts
its objects. This module is the chart geometry: a deterministic subset that can
be drawn without that package. It is not waditu/czsc and it is not a reconciled
Chan implementation.

Rules, in order:

1. Inclusion (包含). An incoming bar that contains or is contained by the last
   merged bar is merged with the running direction. Up keeps the higher high
   and higher low; down keeps the lower high and lower low. The first merge
   before a direction exists is treated as up.
2. Fractals (分型) on merged bars. A top needs both a higher high and a higher
   low than both neighbours. A bottom is the strict opposite.
3. Bi (笔). Alternating fractals at least four merged bars apart. A later
   fractal of the same type replaces the previous one when it is more extreme.
4. Segments (线段). A run of at least three bi ends when the next opposite bi
   breaks the feature extreme already inside the run (the lowest down-bi end
   in an up segment, or the highest up-bi end in a down segment).
5. Zhongshu (中枢). Three consecutive bi whose ranges overlap. ``zg`` is the
   lowest of their highs and ``zd`` the highest of their lows. Later bi extend
   the same zone while they still overlap ``[zd, zg]``; the zone prices stay
   fixed once formed.

No divergence, buy/sell points, or multi-level recursion. ``actionable`` and
``qualified`` stay false.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

ALGORITHM = "chan-structure-simplified-v1"
DISCLAIMER = "简化缠论研究视图：包含、分型、笔、线段和笔中枢。不是完整 CZSC，不含背驰和买卖点，未与固定版本 chanlun 对账。"
MIN_MERGED_GAP = 4


@dataclass
class _Merged:
    start_date: str
    end_date: str
    high: float
    low: float
    high_date: str
    low_date: str


@dataclass(frozen=True)
class _Fractal:
    kind: str
    price: float
    date: str
    index: int


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _day(row: dict[str, Any]) -> str | None:
    raw = row.get("date", row.get("trade_date"))
    if raw is None:
        return None
    text = str(raw)[:10]
    return text if len(text) == 10 else None


def _price(value: float) -> float:
    return round(value, 6)


def _empty(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "algorithm": ALGORITHM,
        "qualified": False,
        "actionable": False,
        "reason": reason,
        "bi": [],
        "segments": [],
        "zhongshu": [],
        "disclaimer": DISCLAIMER,
    }


def _merge(rows: list[dict[str, Any]]) -> list[_Merged]:
    merged: list[_Merged] = []
    direction = 0
    for row in rows:
        day = _day(row)
        high, low = _number(row.get("high")), _number(row.get("low"))
        if day is None or high is None or low is None or high < low or low <= 0:
            continue
        if not merged:
            merged.append(_Merged(day, day, high, low, day, day))
            continue
        last = merged[-1]
        included = (high <= last.high and low >= last.low) or (high >= last.high and low <= last.low)
        if included:
            if direction >= 0:
                if high >= last.high:
                    last.high, last.high_date = high, day
                if low >= last.low:
                    last.low, last.low_date = low, day
                direction = 1
            else:
                if high <= last.high:
                    last.high, last.high_date = high, day
                if low <= last.low:
                    last.low, last.low_date = low, day
            last.end_date = day
            continue
        if high > last.high and low > last.low:
            direction = 1
        elif high < last.high and low < last.low:
            direction = -1
        merged.append(_Merged(day, day, high, low, day, day))
    return merged


def _fractals(merged: list[_Merged]) -> list[_Fractal]:
    found: list[_Fractal] = []
    for index in range(1, len(merged) - 1):
        previous, current, nxt = merged[index - 1], merged[index], merged[index + 1]
        top = current.high > previous.high and current.high > nxt.high and current.low > previous.low and current.low > nxt.low
        bottom = current.high < previous.high and current.high < nxt.high and current.low < previous.low and current.low < nxt.low
        if top:
            found.append(_Fractal("top", current.high, current.high_date, index))
        elif bottom:
            found.append(_Fractal("bottom", current.low, current.low_date, index))
    return found


def _replace_same(chosen: list[_Fractal], fractal: _Fractal) -> None:
    previous = chosen[-2]
    if fractal.kind != previous.kind or fractal.index - previous.index < MIN_MERGED_GAP:
        return
    better = (fractal.kind == "top" and fractal.price >= previous.price) or (fractal.kind == "bottom" and fractal.price <= previous.price)
    if better:
        chosen[-2] = fractal
        chosen.pop()


def _strokes(fractals: list[_Fractal]) -> list[dict[str, Any]]:
    chosen: list[_Fractal] = []
    for fractal in fractals:
        if not chosen:
            chosen.append(fractal)
            continue
        last = chosen[-1]
        if fractal.kind == last.kind:
            if fractal.kind == "top" and fractal.price >= last.price:
                chosen[-1] = fractal
            elif fractal.kind == "bottom" and fractal.price <= last.price:
                chosen[-1] = fractal
            continue
        if fractal.index - last.index < MIN_MERGED_GAP:
            if len(chosen) >= 2:
                _replace_same(chosen, fractal)
            continue
        if last.kind == "bottom" and fractal.price <= last.price:
            continue
        if last.kind == "top" and fractal.price >= last.price:
            continue
        chosen.append(fractal)
    strokes: list[dict[str, Any]] = []
    for start, end in zip(chosen, chosen[1:], strict=False):
        strokes.append({
            "start_date": start.date,
            "end_date": end.date,
            "start_price": _price(start.price),
            "end_price": _price(end.price),
            "direction": "up" if start.kind == "bottom" else "down",
        })
    return strokes


def _segments(strokes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    index = 0
    while index + 2 < len(strokes):
        direction = strokes[index]["direction"]
        last = index + 2
        feature = [item["end_price"] for item in strokes[index:last + 1] if item["direction"] != direction]
        cursor = last
        while cursor + 1 < len(strokes) and feature:
            nxt = strokes[cursor + 1]
            if nxt["direction"] == direction:
                cursor += 1
                continue
            extreme = min(feature) if direction == "up" else max(feature)
            if direction == "up" and nxt["end_price"] < extreme:
                break
            if direction == "down" and nxt["end_price"] > extreme:
                break
            feature.append(nxt["end_price"])
            cursor += 1
        end = strokes[cursor]
        segments.append({
            "start_date": strokes[index]["start_date"],
            "end_date": end["end_date"],
            "start_price": strokes[index]["start_price"],
            "end_price": end["end_price"],
            "direction": direction,
            "bi_count": cursor - index + 1,
        })
        if cursor + 1 >= len(strokes):
            break
        index = cursor + 1
    return segments


def _zhongshu(strokes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    zones: list[dict[str, Any]] = []
    index = 0
    while index + 2 < len(strokes):
        window = strokes[index:index + 3]
        highs = [max(item["start_price"], item["end_price"]) for item in window]
        lows = [min(item["start_price"], item["end_price"]) for item in window]
        zg, zd = min(highs), max(lows)
        if zg <= zd:
            index += 1
            continue
        end = index + 2
        while end + 1 < len(strokes):
            nxt = strokes[end + 1]
            high = max(nxt["start_price"], nxt["end_price"])
            low = min(nxt["start_price"], nxt["end_price"])
            if low >= zg or high <= zd:
                break
            end += 1
        zones.append({
            "start_date": strokes[index]["start_date"],
            "end_date": strokes[end]["end_date"],
            "zd": _price(zd),
            "zg": _price(zg),
            "source": "bi",
        })
        index = end + 1
    return zones


def build_chan_structure(rows: list[dict[str, Any]], *, interval: str = "1d") -> dict[str, Any]:
    """Return drawable bi, segments and zhongshu. Never an actionable signal."""
    merged = _merge(rows)
    if len(merged) < 7:
        result = _empty("history_too_short")
        result["interval"] = interval
        return result
    strokes = _strokes(_fractals(merged))
    segments = _segments(strokes)
    zones = _zhongshu(strokes)
    for zone in _zhongshu(segments):
        zone["source"] = "segment"
        zones.append(zone)
    return {
        "available": True,
        "algorithm": ALGORITHM,
        "qualified": False,
        "actionable": False,
        "reason": None,
        "interval": interval,
        "bi": strokes,
        "segments": segments,
        "zhongshu": zones,
        "disclaimer": DISCLAIMER,
    }
