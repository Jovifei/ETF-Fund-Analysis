"""Research-only event replay using the runtime strategy-family evaluator."""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.services.backtest_v05_service import RotationBacktestV05Service
from app.services.strategy_engine import evaluate_strategy_families
from app.services.strategy_replay_contract import build_strategy_replay_contract
from app.utils.indicators_v05 import calculate_indicators


class StrategyFamilyReplayBacktestService(RotationBacktestV05Service):
    """Replay runtime family scoring through the existing audited ledger.

    Forecast, news, owner holdings and intraday execution evidence are not
    available in this daily-bar replay, so the report remains research-only.
    """

    def _strategy_replay_contract(self) -> dict[str, object]:
        return build_strategy_replay_contract(
            self.strategy,
            status="family_selector_replay_partial",
            source=self.__class__.__name__,
            feature_basis="settled_daily_bars",
            reason="runtime_strategy_families_replayed; forecast_news_holding_state_not_replayed",
        )

    @staticmethod
    def _as_indicator_frame(history: pd.DataFrame) -> pd.DataFrame:
        frame = history.reset_index()
        if "trade_date" not in frame.columns:
            frame = frame.rename(columns={frame.columns[0]: "trade_date"})
        return frame[["trade_date", "open", "high", "low", "close", "volume", "amount"]]

    def _feature_table(self, frames: dict[str, pd.DataFrame], as_of: date) -> pd.DataFrame:
        table = super()._feature_table(frames, as_of)
        if table.empty:
            return table

        values_by_code: dict[str, dict] = {}
        for code in table.index:
            history = frames[code].loc[frames[code].index <= as_of]
            try:
                result = calculate_indicators(
                    self._as_indicator_frame(history), self.strategy["indicator"]
                )
            except (KeyError, TypeError, ValueError):
                continue
            values = dict(result.values)
            values["close"] = float(table.loc[code, "close"])
            values_by_code[code] = values

        if not values_by_code:
            return table.iloc[0:0]

        table = table.loc[table.index.intersection(values_by_code)].copy()
        table["rps20"] = self._percentile_rank(table["return_20"]) * 100
        table["rps60"] = self._percentile_rank(table["return_60"]) * 100
        table["rps120"] = table["rps60"]

        scores: dict[str, float] = {}
        family_scores: dict[str, dict] = {}
        for code in table.index:
            values = values_by_code[code]
            values.update({
                "rps20": float(table.loc[code, "rps20"]),
                "rps60": float(table.loc[code, "rps60"]),
                "rps120": float(table.loc[code, "rps120"]),
            })
            evaluation = evaluate_strategy_families(
                values, self.strategy.get("strategy_engine") or {}
            )
            scores[code] = evaluation.composite_score / 100.0
            family_scores[code] = evaluation.family_scores

        table["score"] = pd.Series(scores)
        table["strategy_family_scores"] = pd.Series(family_scores)
        table["absolute_momentum"] = (
            table["return_20"] * 0.55
            + table["return_60"] * 0.30
            + table["trend_20"] * 0.15
        )
        return table.sort_values("score", ascending=False)


__all__ = ["StrategyFamilyReplayBacktestService"]
