"""Runtime-family/action *projection* on settled daily bars, not a PIT strategy replay.

This shares runtime computation and state transitions, but never invents
historical forecasts, owner holdings, executable quotes or news evidence.
"""
from __future__ import annotations

from datetime import date, datetime, time
import math
from types import SimpleNamespace

import pandas as pd

from app.services.backtest_v05_service import RotationBacktestV05Service
from app.services.constrained_event_execution import ConstrainedEventExecution
from app.services.signal_service import CandidateSignal, blended_signal_score, raw_signal_target
from app.services.signal_v05_service import SignalV05Service
from app.services.strategy_engine import evaluate_strategy_families
from app.services.strategy_replay_contract import build_strategy_replay_contract
from app.utils.indicators_v05 import calculate_indicators
from app.utils.numbers import clamp


NOT_REPLAYED = (
    "14:30_5m_15m_historical_observations_and_first_executable_price",
    "historical_pit_news_and_theme_lineage",
    "historical_forecast_snapshots_and_calibration",
    "real_owner_holdings_and_quote_premium",
    "historical_intraday_signal_hysteresis",
    "full_runtime_preflight_and_snapshot_qualification",
    "historical_universe_membership_and_data_revisions",
)


class StrategyFamilyReplayBacktestService(RotationBacktestV05Service):
    """Reuse live rules on simulated holdings; keep the output research-only."""

    def __init__(self, settings=None) -> None:
        super().__init__(settings)
        self.signal_runtime = SignalV05Service(self.settings)
        self.event_engine = ConstrainedEventExecution(self.config, self.strategy["signal"])
        self._instruments: dict[str, object] = {}
        self._prior_actions: dict[str, object] = {}
        self._pending_cap = 0.0

    def _strategy_replay_contract(self) -> dict[str, object]:
        return build_strategy_replay_contract(
            self.strategy,
            status="family_action_projection_partial",
            source=self.__class__.__name__,
            feature_basis="settled_daily_bars",
            reason="runtime_family_and_signal_state_rules_shared; forecast_news_holding_state_not_replayed",
            not_replayed=list(NOT_REPLAYED),
        )

    @staticmethod
    def _as_indicator_frame(history: pd.DataFrame) -> pd.DataFrame:
        frame = history.reset_index()
        if "trade_date" not in frame.columns:
            frame = frame.rename(columns={frame.columns[0]: "trade_date"})
        return frame[["trade_date", "open", "high", "low", "close", "volume", "amount"]]

    def _load_frames(self, db):
        loaded = super()._load_frames(db)
        self._instruments = loaded[0]
        return loaded

    @staticmethod
    def _rps(values_by_code: dict[str, dict], key: str) -> dict[str, float]:
        usable = {
            code: float(values[key])
            for code, values in values_by_code.items()
            if values.get(key) is not None
            and isinstance(values[key], (int, float))
            and math.isfinite(float(values[key]))
        }
        if len(usable) < 3:
            return {code: 50.0 for code in values_by_code}
        ranked = pd.Series(usable, dtype=float).rank(method="average", pct=True) * 100
        return {code: round(float(ranked.get(code, 50.0)), 2) for code in values_by_code}

    def _feature_table(self, frames: dict[str, pd.DataFrame], as_of: date) -> pd.DataFrame:
        # The inherited selector provides only price-derived warmup/momentum
        # and does not decide the final ranking here.
        table = super()._feature_table(frames, as_of)
        if table.empty:
            return table
        values_by_code: dict[str, dict] = {}
        results: dict[str, object] = {}
        for code in table.index:
            history = frames[code].loc[frames[code].index <= as_of]
            try:
                result = calculate_indicators(
                    self._as_indicator_frame(history), self.strategy["indicator"]
                )
            except (KeyError, TypeError, ValueError):
                continue
            values_by_code[code] = dict(result.values)
            values_by_code[code]["close"] = float(table.loc[code, "close"])
            results[code] = result
        if not values_by_code:
            return table.iloc[0:0]
        table = table.loc[table.index.intersection(values_by_code)].copy()
        for days in (20, 60, 120):
            ranks = self._rps(values_by_code, f"return_{days}d")
            for code in values_by_code:
                values_by_code[code][f"rps{days}"] = ranks[code]

        scored = {}
        for code in table.index:
            values = values_by_code[code]
            base = results[code]
            family = evaluate_strategy_families(values, self.strategy.get("strategy_engine") or {})
            technical = round(clamp(base.technical_score * .25 + family.composite_score * .75, 0, 100), 2)
            risk = round(clamp(base.risk_score + min(12, 4 * len(family.risks)), 0, 100), 2)
            quality, quality_risks = self.signal_runtime._fund_quality(
                None, SimpleNamespace(values_json=values)
            )
            # Only neutral explicit placeholders here. This is a *projection*
            # of the formula, NOT the historical SignalV05 blended score.
            score = blended_signal_score(technical, risk, 50., 50., 60., quality)
            scored[code] = {
                "score": family.composite_score / 100.,
                "signal_score": score,
                "family_scores": family.family_scores,
                "composite_score": family.composite_score,
                "technical_score": technical,
                "risk_score": risk,
                "data_quality": base.data_quality,
                "quality_score": quality,
                "risk_reasons": family.risks + quality_risks,
            }
        for key in ("score", "signal_score", "family_scores", "composite_score",
                    "technical_score", "risk_score", "data_quality", "quality_score", "risk_reasons"):
            table[key] = pd.Series({code: row[key] for code, row in scored.items()})
        ranked = table.sort_values("signal_score", ascending=False)
        ranked.attrs["as_of_date"] = as_of
        return ranked

    def _regime(self, benchmark: pd.DataFrame, as_of: date) -> tuple[str, float, dict]:
        history = benchmark.loc[benchmark.index <= as_of]
        result = calculate_indicators(self._as_indicator_frame(history), self.strategy["indicator"])
        values = dict(result.values)
        evaluation = evaluate_strategy_families(values, self.strategy.get("strategy_engine") or {})
        risk = round(clamp(result.risk_score + min(12, 4 * len(evaluation.risks)), 0, 100), 2)
        benchmark_code = str(self.strategy["signal"].get("regime_benchmark", "510300.SH")).upper()
        benchmark_instrument = SimpleNamespace(id=0, ts_code=benchmark_code)
        return self.signal_runtime._market_regime(
            [benchmark_instrument],
            {0: SimpleNamespace(risk_score=risk, values_json=values)},
        )

    def _select(
        self, features: pd.DataFrame, instruments: dict,
        positions: dict, day_index: int, exposure_cap: float, *,
        portfolio_equity: float | None = None,
    ) -> tuple[dict[str, float], dict]:
        if features.empty or not portfolio_equity or portfolio_equity <= 0:
            return {}, {"reason": "no_replayable_family_inputs", "not_replayed": list(NOT_REPLAYED)}
        items: list[CandidateSignal] = []
        for code, row in features.iterrows():
            instrument = instruments.get(code)
            if instrument is None:
                continue
            # Today's theme metadata cannot assign groups to historical bars.
            # Keep the runtime allocator but put all unclassified history in
            # one conservative bucket; no modern theme survives into PIT ranks.
            research_instrument = SimpleNamespace(
                id=getattr(instrument, "id", None), ts_code=code,
                kind=getattr(instrument, "kind", "ETF"), theme_l1=None,
            )
            current = positions.get(code)
            weight = (
                current.shares * float(row["close"]) / portfolio_equity
                if current is not None and current.shares > 0 else 0.0
            )
            # Reuse the runtime's portfolio-fit calculation on simulated holdings.
            fit = 60.0 if weight == 0 else max(20.0, 70.0 - weight * 150)
            score = blended_signal_score(
                float(row["technical_score"]), float(row["risk_score"]),
                50., 50., fit, float(row["quality_score"]),
            )
            items.append(CandidateSignal(
                instrument=research_instrument, indicator=None, quote=None, forecasts={},
                holding=None, current_weight=weight, score=score,
                confidence=0.0, data_quality=float(row["data_quality"]),
                reasons=[], risks=list(row["risk_reasons"]),
                theme_score=50.0, fund_quality_score=float(row["quality_score"]),
                raw_target_weight=raw_signal_target(score, weight, self.strategy["signal"]),
                actionable=False,
            ))
        self.signal_runtime._apply_portfolio_constraints(items, exposure_cap)
        now = datetime.combine(features.attrs.get("as_of_date", date(2000, 1, 1)), time(15), tzinfo=self.settings.timezone)
        actions: dict[str, dict] = {}
        targets: dict[str, float] = {}
        for item in items:
            self.signal_runtime._label_state(item)
            previous = self._prior_actions.get(item.instrument.ts_code)
            self.signal_runtime._apply_state_hysteresis(item, previous, now)
            code = item.instrument.ts_code
            self._prior_actions[code] = SimpleNamespace(
                state=item.state, score=item.score, as_of_time=now,
            )
            if item.state != "数据异常" and item.first_step_target_weight > 0:
                targets[code] = item.first_step_target_weight
            kind = {
                "可入场": "entry", "可试探": "probe",
                "减仓": ("hard_reduce" if item.score <= self.strategy["signal"]["hard_reduce_score"] else "reduce"),
                "加仓": "entry", "小幅加仓": "probe",
            }.get(item.state, "observe")
            actions[code] = {
                "state": item.state, "action_kind": kind,
                "score": item.score, "current_weight": round(item.current_weight, 6),
                "raw_target_weight": round(item.raw_target_weight, 6),
                "target_weight": item.target_weight,
                "first_step_target_weight": item.first_step_target_weight,
                "actionable": False,
            }
        self._pending_cap = exposure_cap
        return targets, {
            "rule": "SignalV05_portfolio_label_hysteresis_on_family_projection",
            "actions": actions,
            "not_replayed": list(NOT_REPLAYED),
            "simulated_holdings_only": True,
            "historical_theme_allocation_policy": "conservative_unclassified_shared_bucket",
            "theme_point_in_time_qualified": False,
        }

    def _execute(self, trade_date, day_index, target_weights, frames, positions, cash):
        return self.event_engine.execute(
            trade_date, day_index, target_weights, frames, positions, cash,
            instruments=self._instruments,
            exposure_cap=self._pending_cap,
        )

    def _event_constraint_summary(self):
        return self.event_engine.summary()

    def run(self, db, run_id=None):
        self._prior_actions = {}
        self.event_engine = ConstrainedEventExecution(self.config, self.strategy["signal"])
        result = super().run(db, run_id=run_id)
        return result


__all__ = ["StrategyFamilyReplayBacktestService"]
