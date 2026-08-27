from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import DailyBar, Instrument, ReportArtifact
from app.services.event_service import emit_event
from app.utils.hashing import stable_hash


@dataclass(slots=True)
class Position:
    shares: int = 0
    average_cost: float = 0.0
    opened_index: int = 0


class RotationBacktestService:
    """Daily-bar event-driven audit for the ETF/LOF rotation baseline.

    The decision is formed after day *t* closes and executed at day *t+1* open.
    This prevents the common close-to-close look-ahead error. It is deliberately
    independent from the live signal table: the goal is to audit an explicit,
    frozen research rule before any production strategy promotion.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.strategy = self.settings.load_strategy()
        self.config = self.strategy.get("backtest", {})

    @staticmethod
    def _percentile_rank(values: pd.Series) -> pd.Series:
        return values.rank(method="average", pct=True).fillna(0.0)

    def _load_frames(self, db: Session) -> tuple[dict[str, Instrument], dict[str, pd.DataFrame]]:
        instruments = db.scalars(
            select(Instrument).where(Instrument.enabled.is_(True)).order_by(Instrument.ts_code)
        ).all()
        instrument_map = {item.ts_code: item for item in instruments}
        frames: dict[str, pd.DataFrame] = {}
        for instrument in instruments:
            rows = db.scalars(
                select(DailyBar)
                .where(DailyBar.instrument_id == instrument.id)
                .order_by(DailyBar.trade_date)
            ).all()
            if not rows:
                continue
            # If multiple adjustment variants ever coexist, prefer the most recent
            # record for a date while retaining the source in the audit payload.
            frame = pd.DataFrame(
                [
                    {
                        "trade_date": row.trade_date,
                        "open": float(row.open),
                        "high": float(row.high),
                        "low": float(row.low),
                        "close": float(row.close),
                        "volume": float(row.volume or 0.0),
                        "amount": float(row.amount or 0.0),
                        "source": row.source,
                        "fetched_at": row.fetched_at,
                    }
                    for row in rows
                ]
            )
            frame = (
                frame.sort_values(["trade_date", "fetched_at"])
                .drop_duplicates("trade_date", keep="last")
                .set_index("trade_date")
                .sort_index()
            )
            frames[instrument.ts_code] = frame
        return instrument_map, frames

    def _feature_table(self, frames: dict[str, pd.DataFrame], as_of: date) -> pd.DataFrame:
        records: list[dict] = []
        for code, frame in frames.items():
            history = frame.loc[frame.index <= as_of]
            if len(history) < int(self.config.get("minimum_history", 120)):
                continue
            close = history["close"]
            returns = close.pct_change()
            current = float(close.iloc[-1])
            if not math.isfinite(current) or current <= 0:
                continue
            record = {
                "ts_code": code,
                "close": current,
                "return_5": float(current / close.iloc[-6] - 1) if len(close) >= 6 else np.nan,
                "return_20": float(current / close.iloc[-21] - 1) if len(close) >= 21 else np.nan,
                "return_60": float(current / close.iloc[-61] - 1) if len(close) >= 61 else np.nan,
                "trend_20": float(current / close.tail(20).mean() - 1),
                "volatility_20": float(returns.tail(20).std(ddof=0) * np.sqrt(252)),
                "drawdown_60": float(current / close.tail(60).max() - 1),
                "amount_20": float(history["amount"].tail(20).mean()),
            }
            records.append(record)
        if not records:
            return pd.DataFrame()
        table = pd.DataFrame(records).set_index("ts_code")
        required = ["return_5", "return_20", "return_60", "trend_20", "volatility_20"]
        table = table.replace([np.inf, -np.inf], np.nan).dropna(subset=required)
        if table.empty:
            return table

        weights = self.config.get(
            "factor_weights",
            {
                "return_5": 0.15,
                "return_20": 0.35,
                "return_60": 0.25,
                "trend_20": 0.15,
                "low_volatility": 0.10,
            },
        )
        table["rank_return_5"] = self._percentile_rank(table["return_5"])
        table["rank_return_20"] = self._percentile_rank(table["return_20"])
        table["rank_return_60"] = self._percentile_rank(table["return_60"])
        table["rank_trend_20"] = self._percentile_rank(table["trend_20"])
        table["rank_low_volatility"] = 1.0 - self._percentile_rank(table["volatility_20"])
        table["score"] = (
            table["rank_return_5"] * float(weights.get("return_5", 0.15))
            + table["rank_return_20"] * float(weights.get("return_20", 0.35))
            + table["rank_return_60"] * float(weights.get("return_60", 0.25))
            + table["rank_trend_20"] * float(weights.get("trend_20", 0.15))
            + table["rank_low_volatility"] * float(weights.get("low_volatility", 0.10))
        )
        # Absolute momentum is a separate gate. Cross-sectional ranks alone can
        # otherwise select the least-bad ETF during a broad decline.
        table["absolute_momentum"] = (
            table["return_20"] * 0.55 + table["return_60"] * 0.30 + table["trend_20"] * 0.15
        )
        return table.sort_values("score", ascending=False)

    def _regime(self, benchmark: pd.DataFrame, as_of: date) -> tuple[str, float, dict]:
        history = benchmark.loc[benchmark.index <= as_of]
        caps = self.strategy["signal"]["portfolio_exposure_caps"]
        if len(history) < 80:
            return "high_risk", float(caps["high_risk"]), {"reason": "benchmark_history_short"}
        close = history["close"]
        returns = close.pct_change()
        ma20 = float(close.tail(20).mean())
        ma60 = float(close.tail(60).mean())
        rolling_vol = returns.rolling(20).std(ddof=0) * np.sqrt(252)
        current_vol = float(rolling_vol.iloc[-1])
        reference = rolling_vol.tail(252).dropna()
        vol_percentile = float((reference <= current_vol).mean()) if len(reference) else 1.0
        price = float(close.iloc[-1])
        if price < ma60 and vol_percentile >= 0.80:
            label = "extreme_risk"
        elif price < ma60 or vol_percentile >= 0.75:
            label = "high_risk"
        elif price < ma20 or vol_percentile >= 0.45:
            label = "normal"
        else:
            label = "low_risk"
        return label, float(caps[label]), {
            "price": round(price, 6),
            "ma20": round(ma20, 6),
            "ma60": round(ma60, 6),
            "annualized_volatility_20": round(current_vol, 6),
            "volatility_percentile": round(vol_percentile, 4),
        }

    def _select(
        self,
        features: pd.DataFrame,
        instruments: dict[str, Instrument],
        positions: dict[str, Position],
        day_index: int,
        exposure_cap: float,
    ) -> tuple[dict[str, float], dict]:
        if features.empty:
            return {}, {"reason": "no_features"}
        top_n = max(1, int(self.config.get("top_n", 2)))
        minimum_score = float(self.config.get("minimum_cross_section_score", 0.50))
        minimum_momentum = float(self.config.get("minimum_absolute_momentum", 0.0))
        eligible = features[
            (features["score"] >= minimum_score)
            & (features["absolute_momentum"] > minimum_momentum)
        ].copy()
        max_per_theme = max(1, int(self.config.get("max_per_theme", 1)))
        selected: list[str] = []
        theme_counts: dict[str, int] = {}
        for code in eligible.index:
            theme = (instruments.get(code).theme_l1 if instruments.get(code) else None) or "未分类"
            if theme_counts.get(theme, 0) >= max_per_theme:
                continue
            selected.append(code)
            theme_counts[theme] = theme_counts.get(theme, 0) + 1
            if len(selected) >= top_n:
                break

        min_hold_days = int(self.config.get("minimum_hold_days", 9))
        rank_delta = float(self.config.get("rank_hysteresis", 0.10))
        held = [code for code, position in positions.items() if position.shares > 0]
        for code in held:
            if code in selected or code not in features.index:
                continue
            held_days = day_index - positions[code].opened_index
            weakest_code = selected[-1] if selected else None
            weakest_score = float(features.loc[weakest_code, "score"]) if weakest_code else 0.0
            held_score = float(features.loc[code, "score"])
            retain = held_days < min_hold_days or (
                bool(selected) and held_score >= weakest_score - rank_delta
            )
            if retain:
                if weakest_code and weakest_code not in held:
                    selected[-1] = code
                elif len(selected) < top_n:
                    selected.append(code)

        # Stable order and no duplicates after hysteresis replacements.
        selected = sorted(set(selected), key=lambda code: float(features.loc[code, "score"]), reverse=True)[:top_n]
        if not selected:
            return {}, {
                "reason": "no_positive_absolute_momentum",
                "top_scores": [
                    {"ts_code": code, "score": round(float(row.score), 4), "momentum": round(float(row.absolute_momentum), 6)}
                    for code, row in features.head(5).iterrows()
                ],
            }
        single_cap = float(
            self.config.get(
                "single_fund_target_cap",
                self.strategy["signal"].get("single_fund_target_cap", 0.25),
            )
        )
        each = min(exposure_cap / len(selected), single_cap)
        weights = {code: each for code in selected}
        return weights, {
            "selected": selected,
            "target_exposure": round(exposure_cap, 4),
            "scores": {
                code: {
                    "score": round(float(features.loc[code, "score"]), 6),
                    "absolute_momentum": round(float(features.loc[code, "absolute_momentum"]), 6),
                    "volatility_20": round(float(features.loc[code, "volatility_20"]), 6),
                }
                for code in selected
            },
        }

    @staticmethod
    def _commission(value: float, rate: float, minimum: float) -> float:
        return max(minimum, value * rate) if value > 0 else 0.0

    def _execute(
        self,
        trade_date: date,
        day_index: int,
        target_weights: dict[str, float],
        frames: dict[str, pd.DataFrame],
        positions: dict[str, Position],
        cash: float,
    ) -> tuple[float, list[dict]]:
        commission_rate = float(self.config.get("commission_rate", 0.0002))
        minimum_commission = float(self.config.get("minimum_commission", 5.0))
        slippage = float(self.config.get("slippage_rate", 0.0005))
        lot_size = max(1, int(self.config.get("lot_size", 100)))
        open_prices = {
            code: float(frame.loc[trade_date, "open"])
            for code, frame in frames.items()
            if trade_date in frame.index and float(frame.loc[trade_date, "open"]) > 0
        }
        valuation_prices: dict[str, float] = {}
        for code, frame in frames.items():
            if code in open_prices:
                valuation_prices[code] = open_prices[code]
                continue
            history = frame.loc[frame.index < trade_date, "close"]
            if not history.empty and float(history.iloc[-1]) > 0:
                valuation_prices[code] = float(history.iloc[-1])
        equity_at_open = cash + sum(
            position.shares * valuation_prices.get(code, 0.0)
            for code, position in positions.items()
        )
        trades: list[dict] = []

        # Sell first so cash is available for purchases.
        for code in sorted(list(positions)):
            position = positions[code]
            raw_open = open_prices.get(code)
            if not raw_open or position.shares <= 0:
                continue
            target_value = equity_at_open * float(target_weights.get(code, 0.0))
            current_value = position.shares * raw_open
            excess_value = max(0.0, current_value - target_value)
            sell_shares = int(excess_value // (raw_open * lot_size)) * lot_size
            if code not in target_weights:
                sell_shares = position.shares
            sell_shares = min(position.shares, sell_shares)
            if sell_shares <= 0:
                continue
            price = raw_open * (1.0 - slippage)
            gross = price * sell_shares
            fee = self._commission(gross, commission_rate, minimum_commission)
            cash += gross - fee
            realized = (price - position.average_cost) * sell_shares - fee
            position.shares -= sell_shares
            if position.shares <= 0:
                del positions[code]
            trades.append(
                {
                    "date": trade_date.isoformat(),
                    "ts_code": code,
                    "side": "sell",
                    "shares": sell_shares,
                    "price": round(price, 6),
                    "gross": round(gross, 2),
                    "commission": round(fee, 2),
                    "realized_pnl": round(realized, 2),
                }
            )

        for code, weight in sorted(target_weights.items(), key=lambda item: item[1], reverse=True):
            raw_open = open_prices.get(code)
            if not raw_open:
                continue
            position = positions.get(code, Position())
            target_value = equity_at_open * float(weight)
            current_value = position.shares * raw_open
            missing_value = max(0.0, target_value - current_value)
            price = raw_open * (1.0 + slippage)
            buy_shares = int(missing_value // (price * lot_size)) * lot_size
            while buy_shares > 0:
                gross = price * buy_shares
                fee = self._commission(gross, commission_rate, minimum_commission)
                if gross + fee <= cash:
                    break
                buy_shares -= lot_size
            if buy_shares <= 0:
                continue
            gross = price * buy_shares
            fee = self._commission(gross, commission_rate, minimum_commission)
            old_cost = position.average_cost * position.shares
            cash -= gross + fee
            position.average_cost = (old_cost + gross + fee) / (position.shares + buy_shares)
            if position.shares == 0:
                position.opened_index = day_index
            position.shares += buy_shares
            positions[code] = position
            trades.append(
                {
                    "date": trade_date.isoformat(),
                    "ts_code": code,
                    "side": "buy",
                    "shares": buy_shares,
                    "price": round(price, 6),
                    "gross": round(gross, 2),
                    "commission": round(fee, 2),
                    "realized_pnl": 0.0,
                }
            )
        return cash, trades

    @staticmethod
    def _metrics(equity: pd.Series, benchmark: pd.Series, trades: list[dict], exposures: list[float]) -> dict:
        returns = equity.pct_change().dropna()
        total_return = float(equity.iloc[-1] / equity.iloc[0] - 1)
        periods = max(1, len(returns))
        annualized_return = float((1 + total_return) ** (252 / periods) - 1) if total_return > -1 else -1.0
        annualized_volatility = float(returns.std(ddof=0) * np.sqrt(252)) if len(returns) else 0.0
        sharpe = float(returns.mean() / returns.std(ddof=0) * np.sqrt(252)) if len(returns) and returns.std(ddof=0) > 0 else None
        drawdown = equity / equity.cummax() - 1
        max_drawdown = float(drawdown.min())
        calmar = annualized_return / abs(max_drawdown) if max_drawdown < 0 else None
        benchmark_return = float(benchmark.iloc[-1] / benchmark.iloc[0] - 1) if len(benchmark) >= 2 else None
        sell_trades = [item for item in trades if item["side"] == "sell"]
        wins = [item for item in sell_trades if item.get("realized_pnl", 0) > 0]
        gross_turnover = sum(float(item["gross"]) for item in trades)
        return {
            "total_return": round(total_return, 6),
            "annualized_return": round(annualized_return, 6),
            "annualized_volatility": round(annualized_volatility, 6),
            "sharpe_ratio": round(sharpe, 4) if sharpe is not None and math.isfinite(sharpe) else None,
            "max_drawdown": round(max_drawdown, 6),
            "calmar_ratio": round(calmar, 4) if calmar is not None and math.isfinite(calmar) else None,
            "benchmark_return": round(benchmark_return, 6) if benchmark_return is not None else None,
            "excess_return": round(total_return - benchmark_return, 6) if benchmark_return is not None else None,
            "trade_count": len(trades),
            "sell_trade_count": len(sell_trades),
            "realized_win_rate": round(len(wins) / len(sell_trades), 4) if sell_trades else None,
            "turnover_over_initial_equity": round(gross_turnover / float(equity.iloc[0]), 4),
            "average_exposure": round(float(np.mean(exposures)), 4) if exposures else 0.0,
            "final_equity": round(float(equity.iloc[-1]), 2),
        }

    def run(self, db: Session, run_id: str | None = None) -> dict:
        run_id = run_id or uuid4().hex
        instrument_map, frames = self._load_frames(db)
        benchmark_code = str(self.config.get("benchmark", self.strategy["signal"]["regime_benchmark"]))
        benchmark = frames.get(benchmark_code)
        if benchmark is None or benchmark.empty:
            raise ValueError(f"回测缺少基准 {benchmark_code}")
        minimum_history = int(self.config.get("minimum_history", 120))
        calendar = list(benchmark.index)
        if len(calendar) <= minimum_history + 2:
            raise ValueError("日线历史不足，无法执行事件驱动回测")

        initial_cash = float(self.config.get("initial_cash", 1_000_000.0))
        rebalance_days = max(1, int(self.config.get("rebalance_days", 5)))
        cash = initial_cash
        positions: dict[str, Position] = {}
        pending_weights: dict[str, float] | None = None
        pending_reason: dict | None = None
        trades: list[dict] = []
        decisions: list[dict] = []
        equity_records: list[dict] = []
        exposures: list[float] = []
        quality_warnings: list[str] = []

        for code, frame in frames.items():
            daily_jump = frame["close"].pct_change().abs()
            if bool((daily_jump > float(self.config.get("extreme_return_warning", 0.20))).any()):
                quality_warnings.append(f"{code}: 存在绝对日涨跌超过阈值，需核验复权/拆分口径")

        last_decision_index: int | None = None
        for day_index, trade_date in enumerate(calendar):
            if day_index < minimum_history:
                continue
            if pending_weights is not None:
                cash, new_trades = self._execute(
                    trade_date,
                    day_index,
                    pending_weights,
                    frames,
                    positions,
                    cash,
                )
                trades.extend(new_trades)
                if pending_reason is not None:
                    pending_reason["executed_on"] = trade_date.isoformat()
                    pending_reason["trade_count"] = len(new_trades)
                pending_weights = None
                pending_reason = None

            close_values: dict[str, float] = {}
            for code, frame in frames.items():
                history = frame.loc[frame.index <= trade_date, "close"]
                if not history.empty and float(history.iloc[-1]) > 0:
                    close_values[code] = float(history.iloc[-1])
            equity = cash + sum(
                position.shares * close_values.get(code, 0.0)
                for code, position in positions.items()
            )
            invested = sum(
                position.shares * close_values.get(code, 0.0)
                for code, position in positions.items()
            )
            exposure = invested / equity if equity > 0 else 0.0
            exposures.append(exposure)
            equity_records.append(
                {
                    "date": trade_date.isoformat(),
                    "equity": round(equity, 2),
                    "cash": round(cash, 2),
                    "exposure": round(exposure, 6),
                    "positions": {code: position.shares for code, position in positions.items()},
                }
            )

            should_decide = last_decision_index is None or day_index - last_decision_index >= rebalance_days
            if should_decide and day_index < len(calendar) - 1:
                features = self._feature_table(frames, trade_date)
                regime, cap, regime_details = self._regime(benchmark, trade_date)
                target, selection_details = self._select(
                    features, instrument_map, positions, day_index, cap
                )
                decision = {
                    "as_of_close": trade_date.isoformat(),
                    "execution_date": calendar[day_index + 1].isoformat(),
                    "regime": regime,
                    "regime_details": regime_details,
                    "target_weights": {code: round(weight, 6) for code, weight in target.items()},
                    "selection": selection_details,
                    "feature_date_max": trade_date.isoformat(),
                    "no_lookahead": True,
                }
                decisions.append(decision)
                pending_weights = target
                pending_reason = decision
                last_decision_index = day_index

        if len(equity_records) < 2:
            raise ValueError("回测没有形成有效权益序列")
        equity_frame = pd.DataFrame(equity_records)
        equity_series = pd.Series(equity_frame["equity"].to_numpy(), index=pd.to_datetime(equity_frame["date"]))
        benchmark_slice = benchmark.loc[
            (benchmark.index >= date.fromisoformat(equity_frame.iloc[0]["date"]))
            & (benchmark.index <= date.fromisoformat(equity_frame.iloc[-1]["date"])),
            "close",
        ]
        benchmark_series = pd.Series(
            benchmark_slice.to_numpy(dtype=float), index=pd.to_datetime(benchmark_slice.index)
        ).reindex(equity_series.index).ffill().dropna()
        aligned_equity = equity_series.reindex(benchmark_series.index)
        metrics = self._metrics(aligned_equity, benchmark_series, trades, exposures)

        sources = sorted(
            {
                str(frame["source"].dropna().iloc[-1])
                for frame in frames.values()
                if "source" in frame and not frame["source"].dropna().empty
            }
        )
        now = datetime.now(self.settings.timezone)
        payload = {
            "run_id": run_id,
            "generated_at": now.isoformat(),
            "report_type": "rotation_backtest",
            "strategy_version": self.strategy["version"],
            "research_status": "unsealed_research_baseline",
            "promotion_policy": "manual review; requires real-data WFO and independent event-driven comparison",
            "data": {
                "sources": sources,
                "instrument_count": len(frames),
                "start_date": equity_records[0]["date"],
                "end_date": equity_records[-1]["date"],
                "benchmark": benchmark_code,
                "quality_warnings": sorted(set(quality_warnings)),
                "contains_mock": any(source == "mock" for source in sources),
            },
            "configuration": self.config,
            "metrics": metrics,
            "equity_curve": equity_records,
            "decisions": decisions,
            "trades": trades,
            "audit": {
                "decision_at": "close_t",
                "execution_at": "open_t_plus_1",
                "lot_constraint": int(self.config.get("lot_size", 100)),
                "costs_included": True,
                "future_data_in_features": False,
            },
        }
        content_hash = stable_hash(payload)
        self.settings.reports_dir.mkdir(parents=True, exist_ok=True)
        filename = f"rotation_backtest_{now:%Y%m%d_%H%M%S}_{content_hash[:10]}.json"
        path = self.settings.reports_dir / filename
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        db.add(
            ReportArtifact(
                report_type="rotation_backtest",
                as_of_time=now,
                file_path=str(path),
                content_hash=content_hash,
                metadata_json={
                    "run_id": run_id,
                    "filename": filename,
                    "strategy_version": self.strategy["version"],
                    "metrics": metrics,
                    "contains_mock": payload["data"]["contains_mock"],
                },
            )
        )
        db.flush()
        emit_event(db, "backtest.rotation.completed", {"run_id": run_id, "filename": filename})
        return {
            "run_id": run_id,
            "filename": filename,
            "path": str(path),
            "url": f"/api/reports/{filename}",
            "content_hash": content_hash,
            "metrics": metrics,
            "instrument_count": len(frames),
            "decision_count": len(decisions),
        }
