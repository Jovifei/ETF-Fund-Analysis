"""Read-only 14:30 ETF research workbench.

The service combines already persisted market data with deterministic feature,
forecast and support/resistance calculations.  It never creates orders and it
fails closed when a real-time source timestamp is not qualified.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT, Settings, get_settings
from app.models import (
    DailyBar,
    ForecastSnapshot,
    Holding,
    IndicatorSnapshot,
    Instrument,
    NewsItem,
    QuoteSnapshot,
    ReportArtifact,
    SignalSnapshot,
)
from app.services.event_service import emit_event
from app.services.current_decision_service import CurrentDecisionService
from app.utils.feature_store import build_feature_frame
from app.utils.hashing import stable_hash
from app.utils.numbers import clamp
from app.utils.support_resistance import build_support_resistance


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _pct(value: float | None) -> float | None:
    return round(value * 100, 3) if value is not None and math.isfinite(value) else None


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else None


class ETF1430WorkbenchService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.strategy = self.settings.load_strategy()
        path = PROJECT_ROOT / "config" / "etf_1430_workbench.json"
        self.config = json.loads(path.read_text(encoding="utf-8"))
        self.timezone = ZoneInfo(str(self.config.get("decision_timezone", "Asia/Shanghai")))

    @staticmethod
    def _latest(db: Session, model: Any, instrument_id: int, order: Any) -> Any | None:
        return db.scalar(
            select(model).where(model.instrument_id == instrument_id).order_by(order.desc()).limit(1)
        )

    @staticmethod
    def _latest_forecasts(db: Session, instrument_id: int) -> dict[int, ForecastSnapshot]:
        rows = db.scalars(
            select(ForecastSnapshot)
            .where(ForecastSnapshot.instrument_id == instrument_id)
            .order_by(ForecastSnapshot.as_of_date.desc(), ForecastSnapshot.generated_at.desc())
        ).all()
        result: dict[int, ForecastSnapshot] = {}
        for row in rows:
            result.setdefault(int(row.horizon), row)
        return result

    def _raw_and_feature_frame(self, db: Session, instrument_id: int) -> tuple[list[DailyBar], pd.DataFrame]:
        rows = db.scalars(
            select(DailyBar)
            .where(DailyBar.instrument_id == instrument_id)
            .order_by(DailyBar.trade_date)
        ).all()
        if not rows:
            return [], pd.DataFrame()
        raw = pd.DataFrame(
            [
                {
                    "trade_date": row.trade_date,
                    "open": row.open,
                    "high": row.high,
                    "low": row.low,
                    "close": row.close,
                    "volume": row.volume or 0.0,
                    "amount": row.amount or 0.0,
                }
                for row in rows
            ]
        )
        try:
            feature = build_feature_frame(raw, self.strategy["indicator"]).frame
        except Exception:
            feature = pd.DataFrame()
        return list(rows), feature

    def _persisted_forecasts(self, persisted: dict[int, ForecastSnapshot]) -> dict[int, dict[str, Any]]:
        """Read the same persisted forecasts used by the canonical decision board."""
        result: dict[int, dict[str, Any]] = {}
        for horizon_value in self.config.get("forecast_horizons", [1, 3, 5, 10]):
            horizon = int(horizon_value)
            stored = persisted.get(horizon)
            if stored is None:
                result[horizon] = {
                    "horizon": horizon, "source": "unavailable", "model_version": None,
                    "p_up": None, "historical_up_frequency": None, "up_probability": None,
                    "p_up_semantics": "unavailable", "probability_calibrated": False,
                    "expected_return": None, "q10": None, "q50": None, "q90": None,
                    "terminal_price_q10": None, "terminal_price_q50": None, "terminal_price_q90": None,
                    "path_low_price_q10": None, "path_low_price_q50": None, "path_low_price_q90": None,
                    "path_high_price_q10": None, "path_high_price_q50": None, "path_high_price_q90": None,
                    "support_touch_probability": None, "resistance_touch_probability": None,
                    "sample_count": 0, "confidence": 0.0, "similarity_distance": None,
                    "calibration_status": "not_calibrated",
                    "diagnostics": {"reason": "persisted_forecast_missing"},
                }
                continue
            status = str(stored.calibration_status or "not_calibrated")
            calibrated = status == "calibrated"
            result[horizon] = {
                "horizon": horizon, "source": "persisted_forecast_snapshot",
                "model_version": stored.model_version, "p_up": stored.p_up,
                "historical_up_frequency": None if calibrated else stored.p_up,
                "up_probability": stored.p_up if calibrated else None,
                "p_up_semantics": "calibrated_up_probability" if calibrated else "weighted_historical_neighbor_up_frequency",
                "probability_calibrated": calibrated, "expected_return": stored.expected_return,
                "q10": stored.q10, "q50": stored.q50, "q90": stored.q90,
                "terminal_price_q10": stored.terminal_price_q10, "terminal_price_q50": stored.terminal_price_q50, "terminal_price_q90": stored.terminal_price_q90,
                "path_low_price_q10": stored.path_low_price_q10, "path_low_price_q50": stored.path_low_price_q50, "path_low_price_q90": stored.path_low_price_q90,
                "path_high_price_q10": stored.path_high_price_q10, "path_high_price_q50": stored.path_high_price_q50, "path_high_price_q90": stored.path_high_price_q90,
                "support_touch_probability": stored.support_touch_probability, "resistance_touch_probability": stored.resistance_touch_probability,
                "sample_count": stored.sample_count, "confidence": stored.confidence,
                "similarity_distance": stored.similarity_distance, "calibration_status": status,
                "diagnostics": stored.diagnostics_json or {},
            }
        return result

    def _news(self, db: Session, instrument: Instrument) -> list[dict[str, Any]]:
        now = datetime.now(self.timezone)
        cutoff = now - timedelta(hours=int(self.config.get("news_lookback_hours", 72)))
        rows = db.scalars(
            select(NewsItem).where(NewsItem.published_at >= cutoff).order_by(NewsItem.published_at.desc()).limit(100)
        ).all()
        keywords = {
            str(item).strip().casefold()
            for item in (instrument.theme_l1, instrument.theme_l2, instrument.name)
            if item
        }
        matched: list[dict[str, Any]] = []
        for row in rows:
            themes = [str(value) for value in (row.affected_themes_json or [])]
            haystack = " ".join([row.title or "", row.summary or "", *themes]).casefold()
            if not any(keyword and keyword in haystack for keyword in keywords):
                continue
            matched.append(
                {
                    "id": row.id,
                    "title": row.title,
                    "source": row.source,
                    "published_at": _iso(row.published_at),
                    "impact_direction": row.impact_direction,
                    "impact_horizon": row.impact_horizon,
                    "impact_score": row.impact_score,
                    "affected_themes": themes,
                    "facts": row.facts_json or [],
                    "risk_flags": row.risk_flags_json or [],
                }
            )
            if len(matched) >= 8:
                break
        return matched

    @staticmethod
    def _score_trend(values: dict[str, Any], indicator: IndicatorSnapshot | None) -> float:
        score = float(indicator.technical_score) if indicator else 50.0
        ma5, ma10, ma20, ma60 = (_finite(values.get(key)) for key in ("ma5", "ma10", "ma20", "ma60"))
        if None not in (ma5, ma10, ma20, ma60):
            if ma5 > ma10 > ma20 > ma60:
                score += 12
            elif ma5 < ma10 < ma20 < ma60:
                score -= 16
        adx = _finite(values.get("adx14"))
        plus_di = _finite(values.get("plus_di14"))
        minus_di = _finite(values.get("minus_di14"))
        if adx is not None and plus_di is not None and minus_di is not None:
            if adx >= 25 and plus_di > minus_di:
                score += 8
            elif adx >= 25 and plus_di < minus_di:
                score -= 8
        return round(clamp(score, 0, 100), 2)

    @staticmethod
    def _score_momentum(values: dict[str, Any]) -> float:
        score = 50.0
        hist = _finite(values.get("macd_hist"))
        j = _finite(values.get("kdj_j"))
        rsi = _finite(values.get("rsi14"))
        roc = _finite(values.get("roc12"))
        if hist is not None:
            score += 12 if hist > 0 else -12
        if j is not None:
            if 25 <= j <= 80:
                score += 8
            elif j > 100:
                score -= 12
            elif j < 0:
                score += 4
        if rsi is not None:
            if 50 <= rsi <= 68:
                score += 8
            elif rsi >= 75:
                score -= 12
            elif rsi <= 35:
                score -= 6
        if roc is not None:
            score += clamp(roc * 220, -12, 12)
        return round(clamp(score, 0, 100), 2)

    @staticmethod
    def _score_volume(values: dict[str, Any]) -> float:
        score = 50.0
        ratio = _finite(values.get("volume_ratio"))
        mfi = _finite(values.get("mfi14"))
        cmf = _finite(values.get("cmf20"))
        obv_slope = _finite(values.get("obv_slope_5"))
        if ratio is not None:
            score += clamp((ratio - 1.0) * 20, -12, 16)
        if mfi is not None:
            score += clamp((mfi - 50) * 0.35, -14, 14)
        if cmf is not None:
            score += clamp(cmf * 80, -14, 14)
        if obv_slope is not None:
            score += 8 if obv_slope > 0 else -8
        return round(clamp(score, 0, 100), 2)

    @staticmethod
    def _score_forecast(forecasts: dict[int, dict[str, Any]]) -> float:
        weights = {1: 0.35, 3: 0.25, 5: 0.23, 10: 0.17}
        total = 0.0; used = 0.0
        for horizon, weight in weights.items():
            item = forecasts.get(horizon, {}); p_up = _finite(item.get("p_up")); expected = _finite(item.get("expected_return")); confidence = _finite(item.get("confidence"))
            if confidence is not None and confidence <= 1:
                confidence *= 100
            if p_up is None and expected is None:
                continue
            raw = 50.0
            if p_up is not None:
                raw += (p_up - 0.5) * 70
            if expected is not None:
                raw += clamp(expected * 450, -20, 20)
            if confidence is None or confidence < 40:
                value = 50.0
            else:
                evidence = clamp((confidence - 40) / 40, 0, 1)
                if item.get("calibration_status") != "calibrated": evidence *= 0.65
                value = 50.0 + (clamp(raw, 0, 100) - 50.0) * evidence
            total += clamp(value, 0, 100) * weight; used += weight
        return round(total / used, 2) if used else 50.0

    @staticmethod
    def _score_news(news: list[dict[str, Any]]) -> float:
        if not news:
            return 50.0
        net = 0.0
        for item in news:
            direction = str(item.get("impact_direction") or "neutral")
            impact = abs(float(item.get("impact_score") or 0.0))
            net += impact if direction in {"positive", "bullish", "up"} else -impact if direction in {"negative", "bearish", "down"} else 0
        return round(clamp(50 + net * 12, 0, 100), 2)

    def _score_structure(self, sr: dict[str, Any]) -> tuple[float, dict[str, float | None]]:
        current = _finite(sr.get("current_price"))
        support = _finite((sr.get("nearest_support") or {}).get("price"))
        resistance = _finite((sr.get("nearest_resistance") or {}).get("price"))
        downside = current / support - 1 if current and support and support > 0 else None
        upside = resistance / current - 1 if current and resistance and current > 0 else None
        rr = upside / downside if upside is not None and downside is not None and downside > 0 else None
        score = 50.0
        if downside is not None:
            score += clamp((0.06 - downside) * 220, -14, 14)
        if upside is not None:
            score += clamp((upside - 0.04) * 180, -10, 16)
        if rr is not None:
            score += clamp((rr - 1.0) * 12, -12, 18)
        return round(clamp(score, 0, 100), 2), {
            "support": support,
            "resistance": resistance,
            "downside_pct": _pct(downside),
            "upside_pct": _pct(upside),
            "risk_reward": round(rr, 3) if rr is not None and math.isfinite(rr) else None,
        }

    def _decision_window(self, now: datetime) -> dict[str, Any]:
        start_h, start_m = map(int, str(self.config["decision_window"]["start"]).split(":"))
        end_h, end_m = map(int, str(self.config["decision_window"]["end"]).split(":"))
        current = now.astimezone(self.timezone).time().replace(tzinfo=None)
        inside = time(start_h, start_m) <= current <= time(end_h, end_m)
        return {"inside": inside, "start": self.config["decision_window"]["start"], "target": self.config["decision_window"]["target"], "end": self.config["decision_window"]["end"]}

    def _qualification(self, quote: QuoteSnapshot | None, now: datetime) -> dict[str, Any]:
        reasons: list[str] = []
        if self.settings.market_provider == "mock":
            reasons.append("mock_provider")
        if quote is None:
            reasons.append("quote_missing")
        else:
            if not quote.is_realtime:
                reasons.append("quote_not_realtime")
            if not quote.timestamp_verified:
                reasons.append("source_timestamp_unverified")
            if quote.degraded_reason:
                reasons.append("quote_degraded")
            quote_time = quote.quote_time
            if quote_time.tzinfo is None:
                quote_time = quote_time.replace(tzinfo=self.timezone)
            age = (now.astimezone(self.timezone) - quote_time.astimezone(self.timezone)).total_seconds() / 60
            if age > float(self.config["thresholds"].get("maximum_quote_age_minutes", 8)):
                reasons.append("quote_stale")
        window = self._decision_window(now)
        if not window["inside"]:
            reasons.append("outside_1430_window")
        return {
            "actionable": not reasons,
            "research_only": True,
            "reasons": reasons,
            "decision_window": window,
            "historical_1430_backtest": "not_qualified",
        }

    def _scenario_candles(self, frame: pd.DataFrame, forecasts: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
        if frame.empty:
            return []
        horizon_days = sorted(int(value) for value in self.config.get("forecast_horizons", [1, 3, 5, 10]))
        total_days = int(self.config.get("scenario_candles", max(horizon_days)))
        current = float(frame.iloc[-1]["close"])
        anchors_x = [0]
        close_anchors = [current]
        low_anchors = [current]
        high_anchors = [current]
        for horizon in horizon_days:
            item = forecasts.get(horizon, {})
            close_value = _finite(item.get("terminal_price_q50"))
            if close_value is None:
                expected = _finite(item.get("expected_return")) or 0.0
                close_value = current * (1 + expected)
            low_value = _finite(item.get("path_low_price_q50")) or min(current, close_value)
            high_value = _finite(item.get("path_high_price_q50")) or max(current, close_value)
            anchors_x.append(horizon)
            close_anchors.append(close_value)
            low_anchors.append(min(low_value, current, close_value))
            high_anchors.append(max(high_value, current, close_value))
        last_date = pd.Timestamp(frame.iloc[-1]["trade_date"])
        dates = pd.bdate_range(last_date + pd.Timedelta(days=1), periods=total_days)
        candles: list[dict[str, Any]] = []
        previous_close = current
        for day, future_date in enumerate(dates, start=1):
            close_value = float(np.interp(day, anchors_x, close_anchors))
            path_low = float(np.interp(day, anchors_x, low_anchors))
            path_high = float(np.interp(day, anchors_x, high_anchors))
            open_value = previous_close
            low_value = min(path_low, open_value, close_value)
            high_value = max(path_high, open_value, close_value)
            candles.append(
                {
                    "date": future_date.date().isoformat(),
                    "open": round(open_value, 6),
                    "high": round(high_value, 6),
                    "low": round(low_value, 6),
                    "close": round(close_value, 6),
                    "volume": None,
                    "is_forecast": True,
                    "not_actual": True,
                    "scenario": "median_conditional_path",
                    "disclaimer": "预测情景蜡烛，非实际结果",
                }
            )
            previous_close = close_value
        return candles

    def _row(self, db: Session, instrument: Instrument, *, include_chart: bool = False, user_id: int | None = None, current_decision: dict[str, Any] | None = None, decision_snapshot_id: str | None = None) -> dict[str, Any]:
        bars, frame = self._raw_and_feature_frame(db, instrument.id)
        quote = self._latest(db, QuoteSnapshot, instrument.id, QuoteSnapshot.quote_time)
        indicator = self._latest(db, IndicatorSnapshot, instrument.id, IndicatorSnapshot.generated_at)
        signal = self._latest(db, SignalSnapshot, instrument.id, SignalSnapshot.as_of_time)
        holding = db.scalar(select(Holding).where(Holding.instrument_id == instrument.id, Holding.user_id == user_id))
        persisted = self._latest_forecasts(db, instrument.id)
        forecasts = self._persisted_forecasts(persisted)
        if current_decision is None:
            decision_snapshot_id, decision_map = CurrentDecisionService(self.settings).resolve_many(db, [instrument])
            current_decision = decision_map.get(str(instrument.ts_code).strip().upper())
        values = dict(indicator.values_json or {}) if indicator else {}
        if not frame.empty:
            for key, value in frame.iloc[-1].to_dict().items():
                if key not in values and _finite(value) is not None:
                    values[key] = float(value)
        sr = build_support_resistance(frame, self.config.get("support_resistance", {})) if not frame.empty else build_support_resistance(frame)
        news = self._news(db, instrument)
        trend_score = self._score_trend(values, indicator)
        momentum_score = self._score_momentum(values)
        volume_score = self._score_volume(values)
        forecast_score = self._score_forecast(forecasts)
        news_score = self._score_news(news)
        structure_score, structure_metrics = self._score_structure(sr)
        component_scores = {
            "trend": trend_score,
            "momentum": momentum_score,
            "volume_flow": volume_score,
            "structure": structure_score,
            "forecast": forecast_score,
            "news": news_score,
        }
        score = sum(component_scores[name] * float(weight) for name, weight in self.config["weights"].items())
        rr = _finite(structure_metrics.get("risk_reward"))
        action = str((current_decision or {}).get("state") or "数据异常")
        now = datetime.now(self.timezone)
        qualification = self._qualification(quote, now)
        current_price = _finite(quote.price if quote else None) or (_finite(frame.iloc[-1]["close"]) if not frame.empty else None)
        reasons = [
            f"趋势 {trend_score:.1f}",
            f"动量 {momentum_score:.1f}",
            f"量能资金 {volume_score:.1f}",
            f"结构 {structure_score:.1f}",
            f"预测 {forecast_score:.1f}",
        ]
        risks: list[str] = []
        if not qualification["actionable"]:
            risks.append("实时源时间或14:30窗口未通过资格，仅供研究")
        if all(item.get("calibration_status") != "calibrated" for item in forecasts.values()):
            risks.append("1/3/5/10日预测尚未校准")
        if sr.get("chan_zone_approx"):
            risks.append("缠论区间为重叠区近似，不是完整CZSC结果")
        if structure_metrics.get("risk_reward") is not None and float(structure_metrics["risk_reward"]) < float(self.config["thresholds"]["minimum_risk_reward"]):
            risks.append("当前支撑压力风险收益比不足")

        historical = [
            {
                "date": row.trade_date.isoformat(),
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.close,
                "volume": row.volume,
                "is_forecast": False,
            }
            for row in bars[-int(self.config.get("historical_candles", 160)) :]
        ]
        result = {
            "ts_code": instrument.ts_code,
            "name": instrument.name,
            "kind": instrument.kind,
            "theme_l1": instrument.theme_l1,
            "theme_l2": instrument.theme_l2,
            "benchmark": instrument.benchmark,
            "generated_at": now.isoformat(),
            "as_of_date": _iso(bars[-1].trade_date) if bars else None,
            "current_price": current_price,
            "today_pct_change": _finite(quote.pct_change if quote else None),
            "score": round(score, 2),
            "research_score": round(score, 2),
            "score_semantics": "explanatory_ranking_only_not_current_decision",
            "action": action,
            "action_source": (current_decision or {}).get("source", "unavailable"),
            "action_canonical": bool((current_decision or {}).get("canonical", False)),
            "decision_snapshot_id": decision_snapshot_id,
            "current_decision": current_decision or {"state": action, "source": "unavailable", "canonical": False},
            "actionable": bool(qualification["actionable"]),
            "qualification": qualification,
            "component_scores": component_scores,
            "structure_metrics": structure_metrics,
            "support_resistance": sr,
            "forecasts": {str(key): value for key, value in forecasts.items()},
            "indicator": {
                "version": indicator.version if indicator else None,
                "technical_score": indicator.technical_score if indicator else None,
                "risk_score": indicator.risk_score if indicator else None,
                "trend_label": indicator.trend_label if indicator else None,
                "values": values,
            },
            "signal": {
                "state": signal.state,
                "score": signal.score,
                "confidence": signal.confidence,
                "is_actionable": signal.is_actionable,
                "reasons": signal.reasons_json,
                "risks": signal.risks_json,
            }
            if signal
            else None,
            "quote": {
                "source_timestamp": _iso(quote.quote_time),
                "fetched_at": _iso(quote.fetched_at),
                "timestamp_verified": quote.timestamp_verified,
                "is_realtime": quote.is_realtime,
                "source": quote.source,
                "degraded_reason": quote.degraded_reason,
            }
            if quote
            else None,
            "holding": {
                "shares": float(holding.shares or 0),
                "cost_price": float(holding.cost_price or 0),
                "target_weight": holding.target_weight,
            }
            if holding
            else None,
            "news": news,
            "reasons": reasons,
            "risks": risks,
            "governance": self.config["governance"],
        }
        if include_chart:
            result["chart"] = {
                "historical": historical,
                "forecast_scenario": self._scenario_candles(frame, forecasts),
                "forecast_boundary_after": historical[-1]["date"] if historical else None,
                "overlay_modes": ["综合", "均线", "MACD", "KDJ", "RSI", "缠论近似", "成交密集成本"],
            }
        return result

    def summary(self, db: Session, *, user_id: int | None = None) -> dict[str, Any]:
        instruments = db.scalars(
            select(Instrument).where(Instrument.enabled.is_(True)).order_by(Instrument.ts_code)
        ).all()
        decision_snapshot_id, decisions = CurrentDecisionService(self.settings).resolve_many(db, instruments)
        rows = [self._row(db, instrument, include_chart=False, user_id=user_id, current_decision=decisions.get(str(instrument.ts_code).strip().upper()), decision_snapshot_id=decision_snapshot_id) for instrument in instruments]
        rows.sort(key=lambda item: (float(item["research_score"]), item["ts_code"]), reverse=True)
        counts = Counter(item["action"] for item in rows)
        return {
            "version": self.config["version"],
            "generated_at": datetime.now(self.timezone).isoformat(),
            "decision_window": self.config["decision_window"],
            "forecast_horizons": self.config["forecast_horizons"],
            "research_only": True,
            "automatic_orders": False,
            "historical_1430_backtest": "not_qualified",
            "current_decision_contract": "decision_board_snapshot_then_signal_grade_then_signal_snapshot_last_resort",
            "decision_snapshot_id": decision_snapshot_id,
            "score_semantics": "explanatory_ranking_only_not_current_decision",
            "counts": dict(counts),
            "rows": rows,
            "disclaimers": [
                "兼容API的 action 与主页共用唯一 current decision；research_score 只解释和排序，不生成第二套买卖结论。",
                "本页只生成研究结果，不连接券商、不创建订单。",
                "未来蜡烛是条件化情景可视化，不是实际未来OHLC。",
                "真实14:30策略结论必须使用截至14:30的5/15分钟point-in-time数据验证。",
            ],
        }

    def detail(self, db: Session, ts_code: str, *, user_id: int | None = None) -> dict[str, Any] | None:
        instrument = db.scalar(select(Instrument).where(Instrument.ts_code == ts_code.upper()))
        if instrument is None:
            return None
        decision_snapshot_id, decisions = CurrentDecisionService(self.settings).resolve_many(db, [instrument])
        return self._row(db, instrument, include_chart=True, user_id=user_id, current_decision=decisions.get(str(instrument.ts_code).strip().upper()), decision_snapshot_id=decision_snapshot_id)

    def generate_report(self, db: Session, *, user_id: int | None = None) -> dict[str, Any]:
        payload = self.summary(db, user_id=user_id)
        now = datetime.now(self.timezone)
        stamp = now.strftime("%Y%m%d_%H%M%S_%f")
        self.settings.reports_dir.mkdir(parents=True, exist_ok=True)
        filename = f"etf_1430_decision_{stamp}_{stable_hash(payload)[:10]}.json"
        report_dir = self.settings.reports_dir / (f"user-{user_id}" if user_id is not None else "system")
        report_dir.mkdir(parents=True, exist_ok=True)
        path = (report_dir / filename).resolve()
        reports_root = report_dir.resolve()
        if reports_root not in path.parents:
            raise RuntimeError("invalid report path")
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        content_hash = stable_hash(payload)
        db.add(
            ReportArtifact(
                user_id=user_id,
                report_type="etf_1430",
                as_of_time=now,
                file_path=str(path),
                content_hash=content_hash,
                metadata_json={
                    "scope": "private" if user_id is not None else "system",
                    "filename": filename,
                    "instrument_count": len(payload["rows"]),
                    "generated_at": payload["generated_at"],
                },
            )
        )
        db.flush()
        if user_id is not None:
            emit_event(db, "report.generated", {"filename": filename, "user_id": user_id, "report_type": "etf_1430"})
        return {
            "status": "ok",
            "filename": filename,
            "path": str(path),
            "generated_at": payload["generated_at"],
            "instrument_count": len(payload["rows"]),
            "research_only": True,
            "automatic_orders": False,
            "url": f"/api/reports/{filename}" if user_id is not None else None,
            "content_hash": content_hash,
        }
