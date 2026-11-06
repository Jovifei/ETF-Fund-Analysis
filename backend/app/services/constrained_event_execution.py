"""Fail-closed daily event execution for *research* strategy replay.

Without independently verified historical limit, theme, premium and execution
fields, the engine records a blocked order rather than assuming a fill.
No broker or live order interface is present.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
import math
from typing import Any, Mapping

import pandas as pd
import numpy as np

from app.services.backtest_service import Position, RotationBacktestService


def _finite(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _verified(row: pd.Series, field: str) -> bool:
    value = row.get(field)
    return value is True or (isinstance(value, np.bool_) and bool(value))


def _verified_false(row: pd.Series, field: str) -> bool:
    value = row.get(field)
    return isinstance(value, (bool, np.bool_)) and not bool(value)


class ConstrainedEventExecution:
    """Persistent T+1 share-lot ledger, cash book and blocked-order evidence."""

    def __init__(self, config: Mapping[str, Any], signal: Mapping[str, Any]) -> None:
        self.config = config
        self.signal = signal
        self.lots: dict[str, list[tuple[int, int]]] = {}
        self.blocked: list[dict[str, Any]] = []

    def _block(self, day: date, code: str, side: str, reason: str) -> None:
        self.blocked.append({
            "date": day.isoformat(), "ts_code": code,
            "side": side, "reason": reason,
        })

    def _row(self, frame: pd.DataFrame | None, day: date, side: str) -> tuple[pd.Series | None, str | None]:
        if frame is None or day not in frame.index:
            return None, "minute_or_daily_execution_bar_missing"
        row = frame.loc[day]
        if not isinstance(row, pd.Series):
            return None, "duplicate_execution_timestamp"
        op = _finite(row.get("open"))
        if op is None or op <= 0 or not _verified(row, "trade_activity_observed"):
            return None, "suspended_or_unverified_trading_activity"
        if not _verified(row, "execution_price_pit_verified"):
            return None, "first_executable_price_pit_unverified"
        if not _verified(row, "price_limit_verified"):
            return None, "historical_price_limit_evidence_missing"
        if side == "buy" and not _verified_false(row, "limit_up"):
            return None, "buy_blocked_at_limit_up_or_unknown"
        if side == "sell" and not _verified_false(row, "limit_down"):
            return None, "sell_blocked_at_limit_down_or_unknown"
        if not _verified(row, "trading_unit_verified"):
            return None, "exchange_lot_unit_unverified"
        return row, None

    def _available_to_sell(self, code: str, position: Position, day_index: int) -> int:
        if code not in self.lots:
            self.lots[code] = [(position.opened_index, position.shares)]
        return sum(q for opened, q in self.lots[code] if opened < day_index)

    def _consume_lots(self, code: str, sold: int, day_index: int) -> None:
        remaining = sold
        kept = []
        for opened, qty in self.lots.get(code, []):
            if opened < day_index:
                used = min(remaining, qty)
                remaining -= used
                qty -= used
            if qty:
                kept.append((opened, qty))
        if remaining:
            raise ValueError("t_plus_one_lot_identity_mismatch")
        self.lots[code] = kept

    def execute(
        self,
        day: date,
        day_index: int,
        targets: Mapping[str, float],
        frames: Mapping[str, pd.DataFrame],
        positions: dict[str, Position],
        cash: float,
        *,
        instruments: Mapping[str, object],
        exposure_cap: float,
    ) -> tuple[float, list[dict[str, Any]]]:
        if not math.isfinite(cash) or cash < 0:
            raise ValueError("cash_book_invalid")
        commission_rate = float(self.config.get("commission_rate", 0.0002))
        minimum_commission = float(self.config.get("minimum_commission", 5))
        slip = float(self.config.get("slippage_rate", 0.0005))
        lot = max(1, int(self.config.get("lot_size", 100)))
        if any(not math.isfinite(v) or v < 0 for v in (commission_rate, minimum_commission, slip)):
            raise ValueError("execution_cost_policy_invalid")
        max_single = float(self.signal.get("single_fund_target_cap", 0.25))
        max_theme = float(self.signal.get("single_theme_target_cap", 0.4))
        cap = _finite(exposure_cap)
        invalid = (
            cap is None or cap < 0 or cap > 1
            or any(_finite(weight) is None or weight < 0 or weight > max_single for weight in targets.values())
            or sum(targets.values()) > cap + 1e-9
        )
        if invalid:
            for code in sorted(targets):
                self._block(day, code, "buy", "portfolio_exposure_or_single_cap_invalid")
            return cash, []

        opened: dict[str, float] = {}
        marks: dict[str, float] = {}
        for code, frame in frames.items():
            if day in frame.index:
                value = _finite(frame.loc[day, "open"])
                if value is not None and value > 0:
                    opened[code] = value
            close = RotationBacktestService._observed_close(frame, day, before=True)
            if close is not None:
                marks[code] = close
        for code, position in positions.items():
            if position.shares > 0 and code not in opened and code not in marks:
                raise ValueError(f"unpriceable_held_position:{code}:{day}")
        equity = cash + sum(pos.shares * opened.get(code, marks.get(code, 0)) for code, pos in positions.items())
        if equity <= 0:
            raise ValueError("portfolio_equity_invalid")
        trades: list[dict[str, Any]] = []

        def record(code: str, side: str, shares: int, price: float, fee: float, realized: float) -> None:
            trades.append({
                "date": day.isoformat(), "ts_code": code, "side": side,
                "shares": shares, "price": round(price, 6),
                "gross": round(shares * price, 2),
                "commission": round(fee, 2),
                "realized_pnl": round(realized, 2),
                "t_plus_one_checked": True,
                "execution_evidence_verified": True,
            })

        # Sells release cash first. T+1 disallows liquidation of shares bought
        # in this very session even if older lots in the same position are sellable.
        for code in sorted(list(positions)):
            pos = positions[code]
            if pos.shares <= 0:
                continue
            price_open = opened.get(code)
            if price_open is None:
                self._block(day, code, "sell", "suspended_or_price_missing")
                continue
            target_value = equity * targets.get(code, 0.0)
            excess = max(0.0, pos.shares * price_open - target_value)
            sell = pos.shares if code not in targets else int(excess // (price_open * lot)) * lot
            sell = min(sell, pos.shares)
            if not sell:
                continue
            row, reason = self._row(frames.get(code), day, "sell")
            if reason:
                self._block(day, code, "sell", reason)
                continue
            available = self._available_to_sell(code, pos, day_index)
            if sell > available:
                self._block(day, code, "sell", "t_plus_one_unsettled_shares")
            sell = min(sell, available)
            if not sell:
                continue
            price = price_open * (1 - slip)
            gross = price * sell
            fee = RotationBacktestService._commission(gross, commission_rate, minimum_commission)
            if gross < fee:
                self._block(day, code, "sell", "fees_exceed_proceeds")
                continue
            cash += gross - fee
            realized = (price - pos.average_cost) * sell - fee
            pos.shares -= sell
            self._consume_lots(code, sell, day_index)
            if pos.shares == 0:
                del positions[code]
                self.lots.pop(code, None)
            record(code, "sell", sell, price, fee, realized)

        theme_value: dict[str, float] = defaultdict(float)
        for code, pos in positions.items():
            inst = instruments.get(code)
            if inst is not None and getattr(inst, "theme_l1", None):
                theme_value[str(inst.theme_l1)] += pos.shares * opened.get(code, marks.get(code, 0))
        for code, weight in sorted(targets.items(), key=lambda item: (-item[1], item[0])):
            if weight <= 0:
                continue
            frame = frames.get(code)
            row, reason = self._row(frame, day, "buy")
            if reason:
                self._block(day, code, "buy", reason)
                continue
            assert row is not None
            inst = instruments.get(code)
            theme = str(getattr(inst, "theme_l1", "") or "")
            if not theme or not _verified(row, "theme_pit_verified"):
                self._block(day, code, "buy", "effective_dated_theme_missing")
                continue
            kind = str(getattr(inst, "kind", "")).upper()
            if "LOF" in kind or "QDII" in kind or _verified(row, "cross_border_fund"):
                premium = _finite(row.get("premium_rate"))
                if not _verified(row, "premium_pit_verified") or premium is None:
                    self._block(day, code, "buy", "lof_qdii_premium_pit_missing")
                    continue
                if abs(premium) > float(self.config.get("max_abs_premium_pct", 2.0)):
                    self._block(day, code, "buy", "lof_qdii_premium_limit")
                    continue
            price_open = opened[code]
            position = positions.get(code, Position())
            current_value = position.shares * price_open
            missing = max(0.0, equity * weight - current_value)
            if missing / equity < float(self.signal.get("small_add_threshold_weight_points", 0.02)):
                self._block(day, code, "buy", "turnover_hysteresis")
                continue
            theme_room = max(0.0, equity * max_theme - theme_value[theme])
            missing = min(missing, theme_room)
            price = price_open * (1 + slip)
            buy = int(missing // (price * lot)) * lot
            while buy > 0:
                gross = buy * price
                fee = RotationBacktestService._commission(gross, commission_rate, minimum_commission)
                if gross + fee <= cash:
                    break
                buy -= lot
            if not buy:
                self._block(day, code, "buy", "lot_cash_or_theme_cap")
                continue
            gross = buy * price
            fee = RotationBacktestService._commission(gross, commission_rate, minimum_commission)
            old_cost = position.average_cost * position.shares
            cash -= gross + fee
            position.average_cost = (old_cost + gross + fee) / (position.shares + buy)
            if position.shares == 0:
                position.opened_index = day_index
            position.shares += buy
            positions[code] = position
            self.lots.setdefault(code, []).append((day_index, buy))
            theme_value[theme] += buy * price_open
            record(code, "buy", buy, price, fee, 0.0)
        return cash, trades

    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = defaultdict(int)
        for item in self.blocked:
            counts[item["reason"]] += 1
        return {
            "status": "research_constraints_enforced_but_not_pit_qualified",
            "constraints": [
                "t_plus_one", "commission", "slippage", "exchange_lot",
                "limit_up_down", "suspension", "lof_qdii_premium",
                "portfolio_exposure", "single_fund", "effective_dated_theme",
                "turnover_hysteresis",
            ],
            "blocked_order_count": len(self.blocked),
            "blocked_by_reason": dict(sorted(counts.items())),
            "blocked_examples": self.blocked[:25],
            "source_execution_pit_qualified": False,
            "point_in_time_theme_qualified": False,
            "actionable": False,
        }
