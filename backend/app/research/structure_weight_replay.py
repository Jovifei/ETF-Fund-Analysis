"""Offline, research-only R0/R1/R2 experiment. No provider, DB, API or broker.

Inputs are pre-structure base grades and effective-dated data, not current
positions or independently verified historical evidence. This harness does not
reconstruct the rule tree from today's inputs or qualify an untouched holdout.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import re
import shutil
import tempfile
from collections import Counter
from datetime import date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.research import structure_decision, structure_shadow
from app.research.structure_decision import GRADE_RANK, apply_structure_decision
from app.research.structure_shadow import compute_structure_shadow
from app.utils.time_split import purged_expanding_walk_forward_folds, purged_holdout_bounds

VERSION = "structure-weight-replay-v1"
BASELINE_SHA = "1ec6f38281598d76f6208c96c85704ff9aab8a82"
KNOWN_SEEN_THROUGH = "2026-11-10"
FROZEN_FORMULA_SHA256 = {
    "structure_shadow.py": "4cf4a0c59823d5c1e83068ae49e77b7e4d07254e204bc3e0085c02cb688a674c",
    "structure_decision.py": "cf2f8c75318b8fdacb678bbddced5b70f21f425eb027a158b37bcf838512872b",
}
CANDIDATES = (("R0", 0.0), ("R1", 0.3125), ("R2", 0.4167))
STRATEGIES = ("R0", "R1", "R2", "always_long", "momentum_5d")
EXPOSURES = (0.0, 0.0, 0.25, 0.5, 1.0)
HORIZONS = (5, 20)
INITIAL_CASH = 1_000_000.0
LOT_SIZE = 100
TZ = ZoneInfo("Asia/Shanghai")


class ReplayError(ValueError):
    """Input identity/schema errors must not quietly become valid evidence."""


def _json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ReplayError("non_finite_json_or_non_json_input") from exc


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _finite(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _positive(value: Any) -> bool:
    return _finite(value) and value > 0


def _date(value: Any) -> str:
    try:
        if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise ReplayError("invalid_date") from exc
    return value


def _time(value: Any) -> datetime:
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo is None or result.utcoffset() is None:
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise ReplayError("timestamp_timezone_missing_or_invalid") from exc
    return result.astimezone(TZ)


def _open(day: str) -> datetime:
    return datetime.combine(date.fromisoformat(day), time(9, 30), TZ)


def _open_known(bar: dict | None, day: str, as_of: datetime) -> bool:
    if bar is None:
        return False
    try:
        available = _time(bar.get("open_available_at"))
        return available.date().isoformat() == day and available <= min(_open(day), as_of)
    except ReplayError:
        return False


def _close_known(bar: dict | None, day: str, as_of: datetime) -> bool:
    if bar is None:
        return False
    try:
        available = _time(bar.get("close_available_at", bar.get("available_at")))
        cutoff = datetime.combine(date.fromisoformat(day), time(16), TZ)
        return available.date().isoformat() == day and available <= min(cutoff, as_of)
    except ReplayError:
        return False


def _index(rows: Any, universe: list[str], calendar: list[str], kind: str) -> dict:
    if not isinstance(rows, list):
        raise ReplayError(kind + "_rows_not_array")
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ReplayError(kind + "_row_not_object")
        key = (row.get("date"), row.get("code"))
        if key[0] not in calendar or key[1] not in universe:
            raise ReplayError(kind + "_outside_frozen_universe_or_calendar")
        if key in result:
            raise ReplayError("duplicate_" + kind + ":" + str(key))
        result[key] = row
    return result


def _shadow(block: Any) -> dict | None:
    # Runtime accepts more permissive numbers. Research rejects implausible
    # scores/confidence to the same explicit missing-structure fallback.
    if not isinstance(block, dict):
        return None
    for key in ("wyckoff_score", "dow_score"):
        if not _finite(block.get(key)) or not -1 <= block[key] <= 1:
            return None
    for key in ("wyckoff_confidence", "dow_confidence"):
        if not _finite(block.get(key)) or not 0 <= block[key] <= 1:
            return None
    return compute_structure_shadow(block)


def _momentum(
    calendar: list[str], bars: dict, i: int, code: str, cutoff: datetime
) -> tuple[float | None, str | None]:
    if i < 5:
        return None, "momentum_history_missing"
    history = [bars.get((day, code)) for day in calendar[i - 5 : i + 1]]
    if any(row is None or not _positive(row.get("momentum_close")) for row in history):
        return None, "momentum_history_missing"
    try:
        if any(_time(row.get("available_at")) > cutoff for row in history):
            return None, "momentum_not_point_in_time"
    except ReplayError:
        return None, "momentum_not_point_in_time"
    return history[-1]["momentum_close"] / history[0]["momentum_close"] - 1, None


def _opportunities(
    data: dict, universe: list[str], calendar: list[str], signals: dict, bars: dict
) -> list[dict]:
    result = []
    as_of = _time(data["as_of"])
    frozen = _time(data["frozen_at"])
    seen = data["seen_through"]
    for horizon in HORIZONS:
        for i, day in enumerate(calendar):
            if not data["signal_start"] <= day <= data["signal_end"]:
                continue
            for code in universe:
                signal = signals.get((day, code))
                reasons = []
                grade, shadow, momentum = None, None, None
                if signal is None:
                    reasons.append("signal_missing")
                else:
                    grade = signal.get("base_grade")
                    if grade not in GRADE_RANK and grade != "数据异常":
                        reasons.append("base_grade_invalid")
                    try:
                        cutoff = _time(signal.get("decision_at"))
                        available = _time(signal.get("available_at"))
                        inputs_as_of = _time(signal.get("inputs_as_of"))
                        if (
                            cutoff.date().isoformat() != day
                            or available > cutoff
                            or inputs_as_of > cutoff
                            or cutoff > as_of
                            or (i + 1 < len(calendar) and cutoff >= _open(calendar[i + 1]))
                        ):
                            reasons.append("signal_not_point_in_time")
                        momentum, reason = _momentum(calendar, bars, i, code, cutoff)
                        if reason:
                            reasons.append(reason)
                    except ReplayError:
                        reasons.append("signal_not_point_in_time")
                    shadow = _shadow(signal.get("structure_v1"))
                signal_reasons = list(reasons)
                exit_index = i + 1 + horizon  # next-open entry, then h full sessions
                entry_day = calendar[i + 1] if i + 1 < len(calendar) else None
                exit_day = calendar[exit_index] if exit_index < len(calendar) else None
                forward_return = None
                if exit_day is None or _open(exit_day) > as_of:
                    reasons.append("forward_unmatured")
                else:
                    entry = bars.get((entry_day, code))
                    exit_bar = bars.get((exit_day, code))
                    if entry is None or exit_bar is None:
                        reasons.append("forward_bar_missing")
                    else:
                        try:
                            if any(_time(b.get("available_at")) > as_of for b in (entry, exit_bar)):
                                reasons.append("forward_unmatured")
                        except ReplayError:
                            reasons.append("forward_availability_unknown")
                        if not _open_known(entry, entry_day, as_of) or not _open_known(
                            exit_bar, exit_day, as_of
                        ):
                            reasons.append("forward_open_timing_unverified")
                        if _positive(entry.get("open")) and _positive(exit_bar.get("open")):
                            forward_return = exit_bar["open"] / entry["open"] - 1
                        else:
                            reasons.append("forward_price_invalid")
                grades, details, targets = {}, {}, {}
                if not signal_reasons:
                    for name, weight in CANDIDATES:
                        detail = apply_structure_decision(
                            grade, shadow, {"enabled": True, "weight": weight, "max_shift": 1}
                        )
                        details[name] = detail
                        grades[name] = detail["final_grade"]
                        targets[name] = EXPOSURES[GRADE_RANK[grades[name]]] if grade != "数据异常" else 0.0
                    targets["always_long"] = 0.0 if grade == "数据异常" else 1.0
                    targets["momentum_5d"] = (
                        1.0 if grade != "数据异常" and momentum is not None and momentum > 0 else 0.0
                    )
                sample_class = "development_seen" if day <= seen else "prospective_unverified"
                if sample_class == "prospective_unverified" and frozen >= _open(day):
                    sample_class = "post_freeze_violation"
                result.append(
                    {
                        "horizon": horizon,
                        "date": day,
                        "code": code,
                        "included": not reasons,
                        "signal_eligible": not signal_reasons,
                        "label_eligible": not reasons,
                        "signal_exclusion_reasons": sorted(set(signal_reasons)),
                        "exclusion_reasons": sorted(set(reasons)),
                        "sample_class": sample_class,
                        "entry_date": entry_day,
                        "exit_date": exit_day,
                        "base_grade": grade,
                        "structure_missing": shadow is None,
                        "shadow": shadow,
                        "grades": grades,
                        "adjustments": details,
                        "targets": targets,
                        "momentum_5d": momentum,
                        "forward_return_gross_raw": forward_return if not reasons else None,
                        "theme": signal.get("theme") if signal else None,
                        "theme_provenance": "caller_supplied_not_historical_membership_verified",
                    }
                )
    return result


def _portfolio_blockers(data: dict, calendar: list[str]) -> list[str]:
    source = data["source_manifest"]
    reasons = []
    if source.get("price_adjustment") != "raw":
        reasons.append("reliable_raw_prices_missing")
    if not source.get("raw_price_evidence_ref"):
        reasons.append("raw_price_provenance_missing")
    if not source.get("signal_pit_evidence_ref"):
        reasons.append("base_grade_pit_provenance_missing")
    if not source.get("execution_snapshot_evidence_ref"):
        reasons.append("opening_snapshot_provenance_missing")
    ledger = data.get("corporate_actions")
    if not isinstance(ledger, dict) or not ledger.get("evidence_ref"):
        reasons.append("corporate_action_ledger_missing")
    elif (
        ledger.get("coverage_start", "9999") > calendar[0]
        or ledger.get("coverage_end", "") < calendar[-1]
        or not isinstance(ledger.get("events"), list)
    ):
        reasons.append("corporate_action_coverage_incomplete")
    elif ledger["events"]:
        # Draft does not guess split, ex-dividend, pay-date, entitlement or tax
        # handling. A supplied non-empty ledger is not silently discarded.
        reasons.append("corporate_action_processing_not_supported")
    return reasons


def _tradeable(bar: dict | None) -> bool:
    return bar is not None and _positive(bar.get("open")) and _positive(bar.get("open_volume"))


def _simulate(
    calendar: list[str],
    universe: list[str],
    bars: dict,
    rows: list[dict],
    horizon: int,
    phase: int,
    cost_multiplier: int,
    start_index: int,
    end_index: int,
    as_of: datetime,
) -> dict | None:
    indexed = {(row["date"], row["code"]): row for row in rows if row["horizon"] == horizon}
    schedule = list(range(start_index + phase, end_index + 1, horizon))
    # The endpoint is determined by the predeclared schedule, never by
    # future prices, missing exit bars or successful sample labels.
    if not schedule:
        return None
    last_signal = schedule[-1]
    terminal_index = last_signal + 1 + horizon
    first_index = start_index + phase + 1
    if terminal_index >= len(calendar) or _open(calendar[terminal_index]) > as_of:
        return None
    commission, minimum, slip = 0.0002 * cost_multiplier, 5.0 * cost_multiplier, 0.0005 * cost_multiplier
    books = {}
    for strategy in STRATEGIES:
        cash, previous_nav, peak = INITIAL_CASH, INITIAL_CASH, INITIAL_CASH
        shares = dict.fromkeys(universe, 0)
        marks = {}
        trades, daily = [], []
        fee_total = slip_total = notional_total = 0.0
        for i in range(first_index, terminal_index + 1):
            day = calendar[i]
            current = {
                code: bars.get((day, code)) if _open_known(bars.get((day, code)), day, as_of) else None
                for code in universe
            }
            close_current = {
                code: bars.get((day, code)) if _close_known(bars.get((day, code)), day, as_of) else None
                for code in universe
            }
            unavailable = [code for code in universe if current[code] is None]
            for code in universe:
                bar = current[code]
                if bar and _positive(bar.get("open")):
                    marks[code] = bar["open"]
            opening_nav = cash + sum(shares[c] * marks.get(c, 0.0) for c in universe)
            terminal = i == terminal_index
            rebalance = i - 1 in schedule and i - 1 <= last_signal
            if rebalance or terminal:
                desired = {}
                for code in universe:
                    if terminal:
                        desired[code] = 0
                    else:
                        row = indexed[(calendar[i - 1], code)]
                        target = row["targets"].get(strategy, 0.0) if row["signal_eligible"] else 0.0
                        price = current[code].get("open") if current[code] else None
                        # Cannot size without an executable quote; record an
                        # attempted transition and preserve existing shares.
                        if not _positive(price):
                            desired[code] = shares[code]
                            if target > 0 or shares[code]:
                                trades.append(
                                    {
                                        "date": day,
                                        "code": code,
                                        "side": "unknown",
                                        "status": "blocked",
                                        "reason": "invalid_open",
                                        "terminal": terminal,
                                        "shares": 0,
                                    }
                                )
                            continue
                        desired[code] = (
                            math.floor(opening_nav * target / len(universe) / price / LOT_SIZE) * LOT_SIZE
                        )
                # Sells first. All buys share available cash pro rata; never
                # lexicographically favour one ETF when costs make 100% targets unaffordable.
                sell_requests = [(c, shares[c] - desired[c]) for c in universe if shares[c] > desired[c]]
                buy_requests = [(c, desired[c] - shares[c]) for c in universe if desired[c] > shares[c]]
                valid_buys = [(c, q) for c, q in buy_requests if _tradeable(current[c])]
                for side, requests in (("sell", sell_requests), ("buy", buy_requests)):
                    buy_scale = 1.0
                    if side == "buy":
                        needed = sum(
                            q * current[c]["open"] * (1 + slip)
                            + max(minimum, q * current[c]["open"] * (1 + slip) * commission)
                            for c, q in valid_buys
                        )
                        buy_scale = min(1.0, cash / needed) if needed else 1.0
                    for code, requested in requests:
                        bar = current[code]
                        if not _tradeable(bar):
                            trades.append(
                                {
                                    "date": day,
                                    "code": code,
                                    "side": side,
                                    "status": "blocked",
                                    "reason": "invalid_open_or_no_volume",
                                    "terminal": terminal,
                                    "shares": requested,
                                }
                            )
                            continue
                        quantity = (
                            requested
                            if side == "sell"
                            else math.floor(requested * buy_scale / LOT_SIZE) * LOT_SIZE
                        )
                        price = bar["open"] * (1 + slip if side == "buy" else 1 - slip)
                        fee = max(minimum, quantity * price * commission) if quantity else 0.0
                        if side == "buy":
                            while quantity and quantity * price + fee > cash + 1e-8:
                                quantity -= LOT_SIZE
                                fee = max(minimum, quantity * price * commission) if quantity else 0.0
                        if not quantity or (side == "sell" and quantity * price < fee):
                            trades.append(
                                {
                                    "date": day,
                                    "code": code,
                                    "side": side,
                                    "status": "blocked",
                                    "reason": "cash_or_minimum_fee_constraint",
                                    "terminal": terminal,
                                    "shares": requested,
                                }
                            )
                            continue
                        notional = quantity * price
                        slippage_cost = quantity * bar["open"] * slip
                        cash += notional - fee if side == "sell" else -notional - fee
                        shares[code] += -quantity if side == "sell" else quantity
                        fee_total += fee
                        slip_total += slippage_cost
                        notional_total += quantity * bar["open"]
                        trades.append(
                            {
                                "date": day,
                                "signal_date": calendar[i - 1] if not terminal else None,
                                "code": code,
                                "side": side,
                                "status": "filled" if quantity == requested else "partially_filled",
                                "shares": quantity,
                                "unfilled_shares": requested - quantity,
                                "requested_shares": requested,
                                "price": price,
                                "raw_open": bar["open"],
                                "notional": notional,
                                "commission": fee,
                                "slippage_cost": slippage_cost,
                                "cash_after": cash,
                                "terminal": terminal,
                                "grade_changed": (
                                    not terminal
                                    and strategy in dict(CANDIDATES)
                                    and indexed[(calendar[i - 1], code)]["adjustments"]
                                    .get(strategy, {})
                                    .get("applied", False)
                                ),
                            }
                        )
                if cash < -1e-7 or any(q < 0 for q in shares.values()):
                    raise AssertionError("cash_or_shares_invariant_broken")
            stale = []
            for code in universe:
                bar = close_current[code]
                if bar and _positive(bar.get("close")):
                    marks[code] = bar["close"]
                elif shares[code]:
                    stale.append(code)
            market_value = sum(shares[c] * marks.get(c, 0.0) for c in universe)
            nav = cash + market_value
            peak = max(peak, nav)
            daily.append(
                {
                    "date": day,
                    "nav": nav,
                    "cash": cash,
                    "market_value": market_value,
                    "exposure": market_value / nav if nav else 0.0,
                    "return": nav / previous_nav - 1,
                    "drawdown": nav / peak - 1,
                    "stale_marks": stale,
                    "unavailable_bars": unavailable,
                    "shares": dict(shares),
                }
            )
            previous_nav = nav
        filled = [row for row in trades if row["status"] in {"filled", "partially_filled"}]
        fully_filled = [row for row in trades if row["status"] == "filled"]
        returns = sorted(row["return"] for row in daily)
        metrics = {
            "net_return": daily[-1]["nav"] / INITIAL_CASH - 1,
            "max_drawdown": -min(row["drawdown"] for row in daily),
            "average_exposure": sum(row["exposure"] for row in daily) / len(daily),
            "turnover_one_way_over_initial_cash": notional_total / INITIAL_CASH,
            "fees": fee_total,
            "slippage_cost": slip_total,
            "fill_rate_orders": len(fully_filled) / len(trades) if trades else None,
            "any_fill_rate_orders": len(filled) / len(trades) if trades else None,
            "partially_filled_orders": len(filled) - len(fully_filled),
            "filled_orders": len(fully_filled),
            "blocked_orders": len(trades) - len(filled),
            "executed_structure_change_dates": len(
                {r["signal_date"] for r in filled if r.get("grade_changed")}
            ),
            "remaining_shares": sum(shares.values()),
            "fully_liquidated": not any(shares.values()),
            "stale_mark_days": sum(bool(row["stale_marks"]) for row in daily),
            "nav_status": "indicative_stale"
            if any(row["stale_marks"] for row in daily)
            else "conditional_marked",
            "daily_win_rate": sum(v > 0 for v in returns) / len(returns),
            "daily_return_median": _quantile(returns, 0.5),
            "daily_return_p05": _quantile(returns, 0.05),
            "synthetic_or_conditional_simulation_only": True,
            "execution_pit_verified": False,
        }
        books[strategy] = {"metrics": metrics, "trades": trades, "daily_nav": daily}
    return {
        "horizon": horizon,
        "phase": phase,
        "cost_multiplier": cost_multiplier,
        "first_execution_date": calendar[first_index],
        "terminal_date": calendar[terminal_index],
        "strategies": books,
    }


def _quantile(sorted_values: list[float], quantile: float) -> float:
    index = (len(sorted_values) - 1) * quantile
    lo, hi = math.floor(index), math.ceil(index)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (index - lo)


def paired_block_intervals(
    arrays: dict[str, list[float]], *, block_length: int, samples: int = 1000, seed: int = 61111
) -> dict:
    """Moving DATE blocks jointly preserve paired portfolio returns.

    Bonferroni simultaneous intervals for two primary and four secondary
    comparisons. No iid ETF-row bootstrap. Fewer than four blocks => no CI.
    These are descriptive candidate intervals, not approval to promote.
    """
    if not isinstance(block_length, int) or isinstance(block_length, bool) or block_length < 1:
        raise ReplayError("bootstrap_block_invalid")
    if not isinstance(samples, int) or isinstance(samples, bool) or samples < 100:
        raise ReplayError("bootstrap_samples_less_than_100")
    if set(arrays) != set(STRATEGIES) or len({len(v) for v in arrays.values()}) != 1:
        raise ReplayError("paired_arrays_must_share_dates")
    n = len(arrays["R0"])
    if n < 4 * block_length:
        return {}
    if any(not _finite(x) for a in arrays.values() for x in a):
        raise ReplayError("paired_returns_non_finite")
    comparisons = [
        ("R1", "R0", 2),
        ("R2", "R0", 2),
        ("R1", "always_long", 4),
        ("R2", "always_long", 4),
        ("R1", "momentum_5d", 4),
        ("R2", "momentum_5d", 4),
    ]
    deltas = {
        f"{a}-{b}": [x - y for x, y in zip(arrays[a], arrays[b], strict=True)] for a, b, _ in comparisons
    }
    estimates = {key: [] for key in deltas}
    randomizer = random.Random(seed)
    for _ in range(samples):
        positions = []
        while len(positions) < n:
            start = randomizer.randrange(n - block_length + 1)
            positions.extend(range(start, start + block_length))
        positions = positions[:n]
        for key, values in deltas.items():
            estimates[key].append(sum(values[i] for i in positions) / n)
    return {
        f"{a}-{b}": {
            "mean_difference": sum(deltas[f"{a}-{b}"]) / n,
            "lower": _quantile(sorted(estimates[f"{a}-{b}"]), 0.05 / family / 2),
            "upper": _quantile(sorted(estimates[f"{a}-{b}"]), 1 - 0.05 / family / 2),
            "family_comparisons": family,
            "familywise_alpha": 0.05,
            "block_length": block_length,
            "dates": n,
            "samples": samples,
            "seed": seed,
            "effective_nonoverlap_blocks": n // block_length,
            "low_power": n // block_length < 20,
        }
        for a, b, family in comparisons
    }


def _split_report(data: dict, calendar: list[str]) -> dict:
    untouched = [
        day for day in calendar if day > data["seen_through"] and _time(data["frozen_at"]) < _open(day)
    ]
    reasons, folds, holdout = [], [], None
    if untouched:
        start = untouched[0]
        try:
            # Forward labels exit at t+1+h, not t+h: purge 21 sessions.
            holdout = purged_holdout_bounds(calendar, test_start=start, label_horizon=21).model_dump()
            folds = [
                f.model_dump()
                for f in purged_expanding_walk_forward_folds(
                    [d for d in calendar if d < start],
                    label_horizon=21,
                    folds=4,
                    test_sessions=20,
                    min_train_sessions=150,
                )
            ]
        except ValueError as exc:
            reasons.append("insufficient_development_history:" + str(exc))
    else:
        reasons.append("no_post_freeze_unseen_calendar")
    if len(untouched) < 120:
        reasons.append("fewer_than_120_unseen_calendar_sessions")
    reasons.append("independent_holdout_access_and_source_receipts_not_verified")
    return {
        "known_seen_through": data["seen_through"],
        "proposed_final_start": untouched[0] if untouched else None,
        "proposed_unseen_calendar_sessions": len(untouched),
        "holdout_bounds": holdout,
        "walk_forward_folds": folds,
        "label_purge_sessions": 21,
        "final_oos_validated": False,
        "reasons": reasons,
        "review_cadence": "weekly data quality; monthly fixed-spec summaries; no interim retuning",
    }


def _source_hashes() -> dict[str, str]:
    # Hash LF-normalized source bytes: the frozen values are recorded from the
    # committed (LF) blobs, so a Windows CRLF checkout must not read as drift.
    modules = (structure_shadow, structure_decision)
    return {
        Path(module.__file__).name: hashlib.sha256(
            Path(module.__file__).read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()
        for module in modules
    }


def build_report(data: dict, *, expected_config_hash: str, bootstrap_samples: int = 1000) -> dict:
    """Build an entirely in-memory, fail-closed research artifact.

    ``expected_config_hash`` is the SHA256 of exact frozen strategy.json bytes,
    supplied by the offline CLI, not a runtime CONFIG_HASH or an input assertion.
    """
    input_hash = _hash(data)
    if _source_hashes() != FROZEN_FORMULA_SHA256:
        raise ReplayError("frozen_formula_source_changed_review_required")
    if not isinstance(data, dict) or data.get("schema_version") != "structure-weight-input-v1":
        raise ReplayError("input_schema_version_invalid")
    universe = data.get("universe")
    if (
        not isinstance(universe, list)
        or not universe
        or len(universe) != len(set(universe))
        or any(not isinstance(c, str) or not re.fullmatch(r"\d{6}(?:\.(?:SH|SZ))?", c) for c in universe)
    ):
        raise ReplayError("frozen_universe_invalid")
    universe = sorted(universe)
    calendar = data.get("calendar")
    if not isinstance(calendar, list) or not calendar or calendar != sorted(set(calendar)):
        raise ReplayError("exchange_calendar_must_be_sorted_unique")
    for day in calendar:
        _date(day)
    for key in ("signal_start", "signal_end", "seen_through"):
        _date(data.get(key))
    if data["seen_through"] < KNOWN_SEEN_THROUGH:
        raise ReplayError("seen_through_before_known_cutoff")
    if (
        data["signal_start"] not in calendar
        or data["signal_end"] not in calendar
        or data["signal_start"] > data["signal_end"]
    ):
        raise ReplayError("signal_window_invalid")
    _time(data.get("frozen_at"))
    _time(data.get("as_of"))
    source = data.get("source_manifest")
    if not isinstance(source, dict) or source.get("code_sha") != BASELINE_SHA:
        raise ReplayError("source_code_identity_mismatch")
    if (
        not re.fullmatch("[0-9a-f]{64}", expected_config_hash or "")
        or source.get("config_sha256") != expected_config_hash
    ):
        raise ReplayError("source_config_identity_mismatch")
    if source.get("signal_definition") != "base_grade_before_structure":
        raise ReplayError("base_grade_must_precede_structure_adjustment")
    if source.get("momentum_adjustment") != "consistent_total_return":
        raise ReplayError("momentum_adjustment_basis_unknown")
    signals = _index(data.get("signals"), universe, calendar, "signal")
    bars = _index(data.get("bars"), universe, calendar, "bar")
    rows = _opportunities(data, universe, calendar, signals, bars)
    blockers = _portfolio_blockers(data, calendar)
    if blockers:
        for row in rows:
            row["forward_return_gross_raw"] = None
    experiments = {}
    if not blockers:
        for horizon in HORIZONS:
            experiments[str(horizon)] = {}
            for label, multiplier in (("base", 1), ("double_cost", 2)):
                runs = [
                    _simulate(
                        calendar,
                        universe,
                        bars,
                        rows,
                        horizon,
                        phase,
                        multiplier,
                        calendar.index(data["signal_start"]),
                        calendar.index(data["signal_end"]),
                        _time(data["as_of"]),
                    )
                    for phase in range(horizon)
                ]
                primary = runs[0]
                intervals = {}
                if primary and not any(
                    book["metrics"]["stale_mark_days"] for book in primary["strategies"].values()
                ):
                    arrays = {
                        name: [r["return"] for r in primary["strategies"][name]["daily_nav"]]
                        for name in STRATEGIES
                    }
                    for block in (5, 10) if horizon == 5 else (20,):
                        intervals[str(block)] = paired_block_intervals(
                            arrays, block_length=block, samples=bootstrap_samples
                        )
                experiments[str(horizon)][label] = {
                    "primary": primary,
                    "paired_daily_intervals": intervals,
                    "phase_sensitivity": [
                        {
                            "phase": phase,
                            "strategies": {k: v["metrics"] for k, v in run["strategies"].items()},
                        }
                        for phase, run in enumerate(runs)
                        if run
                    ],
                    "interval_empty_means": "insufficient paired blocks, incomplete window, or stale NAV; never a zero effect",
                }
    coverage = {}
    for horizon in HORIZONS:
        subset = [r for r in rows if r["horizon"] == horizon]
        included = [r for r in subset if r["included"]]
        coverage[str(horizon)] = {
            "expected_opportunities": len(subset),
            "common_included": len(included),
            "causal_signal_eligible": sum(r["signal_eligible"] for r in subset),
            "coverage": len(included) / len(subset) if subset else None,
            "excluded_by_reason": dict(Counter(reason for r in subset for reason in r["exclusion_reasons"])),
            "sample_class_counts": dict(Counter(r["sample_class"] for r in included)),
            "base_grade_counts": dict(Counter(str(r["base_grade"]) for r in included)),
            "theme_counts_unverified": dict(Counter(str(r["theme"] or "unknown") for r in included)),
            "structure_fallback_count": sum(r["structure_missing"] for r in included),
            "abnormal_no_new_risk_count": sum(r["base_grade"] == "数据异常" for r in included),
            "changed_decision_dates": {
                name: len({r["date"] for r in included if r["adjustments"][name]["applied"]})
                for name, _ in CANDIDATES
            },
            "active_counts": {name: sum(r["targets"][name] > 0 for r in included) for name in STRATEGIES},
            "grade_shift_counts": {
                name: dict(
                    Counter(
                        "up" if GRADE_RANK[r["grades"][name]] > GRADE_RANK[r["base_grade"]] else "down"
                        for r in included
                        if r["adjustments"][name]["applied"]
                    )
                )
                for name, _ in CANDIDATES
            },
        }
    manifest = {
        "schema_version": VERSION,
        "base_code_sha": BASELINE_SHA,
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "config_sha256": expected_config_hash,
        "formula_source_sha256": _source_hashes(),
        "input_sha256": input_hash,
        "universe": universe,
        "universe_sha256": _hash(universe),
        "calendar_sha256": _hash(calendar),
        "candidates": dict(CANDIDATES),
        "soft_c": {
            "weights_id": structure_shadow.SHADOW_WEIGHTS_ID,
            "wyckoff": structure_shadow.W_WYCKOFF,
            "dow": structure_shadow.W_DOW,
            "confidence_floor": structure_shadow.CONF_FLOOR,
            "buy_threshold": structure_shadow.BUY_THRESH,
            "neutral_band": structure_shadow.FLAT_BAND,
            "atr_scale": dict(structure_shadow.ATR_SCALE),
        },
        "research_policy": {
            "initial_cash": INITIAL_CASH,
            "grade_exposures": list(EXPOSURES),
            "commission_rate": 0.0002,
            "minimum_commission": 5.0,
            "slippage_rate": 0.0005,
            "tax_rate_assumption": 0.0,
            "lot_size_assumption": LOT_SIZE,
            "horizons": list(HORIZONS),
            "entry": "next exchange session open",
            "terminal": "open h sessions after entry; costs included",
            "missing_signal": "causal common exclusion; no new exposure; reduce existing if executable",
            "execution_time": "09:30 Asia/Shanghai; separate available opening snapshot required",
            "daily_valuation_cutoff": "16:00 Asia/Shanghai; late close not used retrospectively",
            "allocation": "target exposure / frozen universe size; residual cash; pro rata affordable buys",
            "bootstrap_seed": 61111,
            "bootstrap_samples": bootstrap_samples,
        },
        "source_manifest": source,
        "frozen_at": data["frozen_at"],
        "as_of": data["as_of"],
    }
    manifest["research_policy_sha256"] = _hash(
        {
            "candidates": manifest["candidates"],
            "soft_c": manifest["soft_c"],
            "research_policy": manifest["research_policy"],
            "formula_source_sha256": manifest["formula_source_sha256"],
        }
    )
    return {
        "status": "signal_only" if blockers else "conditional_simulation",
        "manifest": manifest,
        "integrity": {"portfolio_blockers": blockers, "coverage": coverage},
        "opportunities": rows,
        "experiments": experiments,
        "time_split": _split_report(data, calendar),
        "qualification": {
            "research_only": True,
            "actionable": False,
            "calibration_status": "not_calibrated",
            "final_oos_validated": False,
            "promotion_allowed": False,
        },
        "limitations": [
            "Frozen-pool conditional research; historical constituents/delistings not verified.",
            "Input metadata and receipt references are not independent source or holdout verification.",
            "Base grades must already be point-in-time pre-structure results; rule-tree regeneration is not implemented.",
            "Portfolio is a conditional raw-price/no-corporate-action simulation, not executable return evidence.",
            "Nonempty corporate-action ledger blocks portfolio; no guessed dividend/split treatment.",
            "Limit-order queues, price limits, T+1 instrument exceptions, spreads and market impact are not modeled.",
            "Fixed 100-share lots, zero tax and fees are research assumptions, not broker terms.",
            "Invalid open/no volume means no fill; stale marks and unliquidated shares remain disclosed.",
            "No automatic selection, promotion, production configuration writes or data upload.",
            "Factor correlation and inner-factor ablations are not run without separate PIT feature evidence; R0 is the whole-structure ablation.",
        ],
    }


def write_report(report: dict, target: Path) -> None:
    """Exclusive output directory, atomic publication on a single filesystem."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive reservation prevents concurrent callers replacing a report.
    target.mkdir()
    temporary = Path(tempfile.mkdtemp(prefix=".replay-", dir=target.parent))
    try:
        (temporary / "report.json").write_text(_json(report) + "\n", encoding="utf-8")
        (temporary / "manifest.json").write_text(_json(report["manifest"]) + "\n", encoding="utf-8")
        (temporary / "opportunities.jsonl").write_text(
            "".join(_json(row) + "\n" for row in report["opportunities"]), encoding="utf-8"
        )
        for horizon, modes in report["experiments"].items():
            for label, experiment in modes.items():
                run = experiment["primary"]
                if run is None:
                    continue
                for strategy, book in run["strategies"].items():
                    for kind in ("trades", "daily_nav"):
                        rows = book[kind]
                        (temporary / f"h{horizon}-{label}-{strategy}-{kind}.jsonl").write_text(
                            "".join(_json(row) + "\n" for row in rows), encoding="utf-8"
                        )
        (temporary / "INCOMPLETE").write_text(
            "This marker is removed only after all artifact hashes are written.\n"
        )
        hashes = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in temporary.iterdir()
            if path.name != "INCOMPLETE"
        }
        (temporary / "checksums.json").write_text(_json(hashes) + "\n", encoding="utf-8")
        (temporary / "INCOMPLETE").unlink()
        # Renaming onto the directory we exclusively reserved is atomic on
        # POSIX; Windows forbids renaming a directory onto an existing one,
        # so drop our own (verified-empty) reservation first. A pre-existing
        # user run is never touched: mkdir above already raised for it, and
        # rmdir below cannot succeed on a non-empty directory.
        try:
            os.replace(temporary, target)
        except PermissionError:
            os.rmdir(target)
            os.rename(temporary, target)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        # Leave the reservation visibly incomplete rather than claim success.
        (target / "INCOMPLETE").write_text("Artifact publication failed. Inspect before removal.\n")
        raise
