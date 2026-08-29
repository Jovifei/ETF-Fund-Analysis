from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import MarketClock
from app.core.config import Settings, get_settings
from app.models import (
    ForecastSnapshot,
    Holding,
    IndicatorSnapshot,
    Instrument,
    NewsItem,
    QuoteSnapshot,
    SignalSnapshot,
)
from app.services.event_service import emit_event
from app.services.preflight_service import PreflightService
from app.services.trading_calendar_service import TradingCalendarService
from app.utils.hashing import stable_hash
from app.utils.numbers import clamp


@dataclass(slots=True)
class CandidateSignal:
    instrument: Instrument
    indicator: IndicatorSnapshot | None
    quote: QuoteSnapshot | None
    forecasts: dict[int, ForecastSnapshot]
    holding: Holding | None
    current_weight: float
    score: float
    confidence: float
    data_quality: float
    reasons: list[str]
    risks: list[str]
    theme_score: float
    fund_quality_score: float
    raw_target_weight: float
    target_weight: float = 0.0
    first_step_target_weight: float = 0.0
    state: str = "观察"
    actionable: bool = False


class SignalService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.strategy = self.settings.load_strategy()
        self.preflight = PreflightService(self.settings)
        self.clock = MarketClock(self.settings.timezone)
        self.calendar = TradingCalendarService(self.settings)

    @staticmethod
    def _latest_by_horizon(rows: list[ForecastSnapshot]) -> dict[int, ForecastSnapshot]:
        result: dict[int, ForecastSnapshot] = {}
        for row in rows:
            result.setdefault(row.horizon, row)
        return result

    def _portfolio_weights(self, db: Session, quotes: dict[int, QuoteSnapshot]) -> dict[int, float]:
        holdings = db.scalars(select(Holding)).all()
        values: dict[int, float] = {}
        total = 0.0
        for holding in holdings:
            quote = quotes.get(holding.instrument_id)
            price = quote.price if quote else float(holding.cost_price or 0)
            value = float(holding.shares or Decimal(0)) * float(price or 0)
            values[holding.instrument_id] = value
            total += value
        if total <= 0:
            return {key: 0.0 for key in values}
        return {key: value / total for key, value in values.items()}

    def _news_theme_score(self, db: Session, instrument: Instrument, now: datetime) -> tuple[float, list[str]]:
        cutoff = now - timedelta(hours=72)
        rows = db.scalars(
            select(NewsItem).where(NewsItem.published_at >= cutoff).order_by(NewsItem.published_at.desc())
        ).all()
        themes = {value for value in (instrument.theme_l1, instrument.theme_l2) if value}
        impacts: list[float] = []
        evidence: list[str] = []
        for row in rows:
            matched = any(
                any(theme in affected or affected in theme for affected in row.affected_themes_json)
                for theme in themes
            )
            if not matched:
                continue
            published_at = row.published_at
            if published_at.tzinfo is None:
                published_at = published_at.replace(tzinfo=self.settings.timezone)
            age_hours = max(0.0, (now - published_at).total_seconds() / 3600)
            decay = max(0.2, 1 - age_hours / 96)
            impacts.append(float(row.impact_score or 0) * decay)
            evidence.append(row.title)
        if not impacts:
            return 50.0, []
        score = 50 + 35 * sum(impacts) / max(1, len(impacts))
        return round(clamp(score, 0, 100), 2), evidence[:5]

    @staticmethod
    def _fund_quality(quote: QuoteSnapshot | None, indicator: IndicatorSnapshot | None) -> tuple[float, list[str]]:
        score = 55.0
        risks: list[str] = []
        if quote:
            amount = float(quote.amount or 0)
            if amount >= 100_000_000:
                score += 15
            elif amount >= 20_000_000:
                score += 8
            elif amount and amount < 5_000_000:
                score -= 12
                risks.append("成交额偏低")
            premium = quote.premium_rate
            if premium is not None:
                if abs(premium) > 2:
                    score -= 20
                    risks.append("溢价/折价绝对值超过 2%")
                elif abs(premium) > 1:
                    score -= 8
                    risks.append("溢价/折价绝对值超过 1%")
        if indicator:
            values = indicator.values_json
            drawdown = float(values.get("drawdown_60d") or 0)
            volatility = float(values.get("volatility_20d") or 0)
            if drawdown > -0.08:
                score += 8
            elif drawdown < -0.18:
                score -= 10
                risks.append("近 60 日回撤较深")
            if volatility < 0.22:
                score += 7
            elif volatility > 0.4:
                score -= 10
                risks.append("近 20 日波动率较高")
        return round(clamp(score, 0, 100), 2), risks

    def _market_regime(
        self,
        instruments: list[Instrument],
        indicators: dict[int, IndicatorSnapshot],
    ) -> tuple[str, float, dict]:
        cfg = self.strategy["signal"]
        benchmark_code = str(cfg.get("regime_benchmark", "510300.SH")).upper()
        benchmark = next((item for item in instruments if item.ts_code.upper() == benchmark_code), None)
        indicator = indicators.get(benchmark.id) if benchmark else None
        caps = cfg.get("portfolio_exposure_caps", {})
        if indicator is None:
            return "unknown", float(caps.get("high_risk", 0.4)), {"reason": "benchmark_indicator_missing"}
        values = indicator.values_json or {}
        risk = float(indicator.risk_score)
        volatility = float(values.get("volatility_20d") or 0)
        drawdown = float(values.get("drawdown_60d") or 0)
        if risk >= 78 or volatility >= 0.45 or drawdown <= -0.22:
            label = "extreme_risk"
        elif risk >= 65 or volatility >= 0.34 or drawdown <= -0.15:
            label = "high_risk"
        elif risk <= 45 and volatility <= 0.22 and drawdown >= -0.08:
            label = "low_risk"
        else:
            label = "normal"
        return label, float(caps.get(label, 0.7)), {
            "benchmark": benchmark_code,
            "risk_score": round(risk, 2),
            "volatility_20d": volatility,
            "drawdown_60d": drawdown,
        }

    def _build_candidate(
        self,
        db: Session,
        instrument: Instrument,
        quote: QuoteSnapshot | None,
        indicator: IndicatorSnapshot | None,
        forecasts: dict[int, ForecastSnapshot],
        holding: Holding | None,
        current_weight: float,
        now: datetime,
    ) -> CandidateSignal:
        preflight = self.preflight.check_instrument(db, instrument, now)
        reasons: list[str] = []
        risks = list(preflight.warnings)
        if preflight.missing_optional:
            risks.append("缺少：" + "、".join(preflight.missing_optional))
        if preflight.missing_core:
            risks.append("核心数据缺失：" + "、".join(preflight.missing_core))

        technical = float(indicator.technical_score if indicator else 0)
        risk_score = float(indicator.risk_score if indicator else 100)
        data_quality = float(indicator.data_quality if indicator else 0)
        theme_score, news_evidence = self._news_theme_score(db, instrument, now)
        quality_score, quality_risks = self._fund_quality(quote, indicator)
        risks.extend(quality_risks)

        forecast_scores: list[float] = []
        forecast_confidences: list[float] = []
        forecast_weight = 0.0
        for horizon, weight in ((1, 0.5), (5, 0.3), (20, 0.2)):
            item = forecasts.get(horizon)
            if item and item.p_up is not None:
                forecast_scores.append((float(item.p_up) * 100) * weight)
                forecast_weight += weight
                forecast_confidences.append(float(item.confidence))
        forecast_score = sum(forecast_scores) / forecast_weight if forecast_weight else 50.0

        portfolio_fit = 60.0 if current_weight == 0 else max(20.0, 70.0 - current_weight * 150)
        score = (
            technical * 0.35
            + (100 - risk_score) * 0.20
            + theme_score * 0.20
            + forecast_score * 0.15
            + portfolio_fit * 0.05
            + quality_score * 0.05
        )
        if indicator:
            reasons.extend(indicator.values_json.get("technical_reasons", []))
        if news_evidence:
            reasons.append(f"近 72 小时主题新闻 {len(news_evidence)} 条")
        one_day = forecasts.get(1)
        if one_day and one_day.p_up is not None:
            reasons.append(f"1日上涨概率 {one_day.p_up * 100:.1f}%（{one_day.calibration_status}）")
        if quote and quote.premium_rate is not None:
            reasons.append(f"场内溢价率 {quote.premium_rate:.2f}%")

        if score >= 78:
            raw_target = 0.20
        elif score >= 68:
            raw_target = 0.14
        elif score >= 58:
            raw_target = 0.07
        elif score >= 48 and current_weight > 0:
            raw_target = min(current_weight, 0.05)
        else:
            raw_target = 0.0
        max_cap = float(self.strategy["signal"]["single_fund_target_cap"])
        raw_target = min(raw_target, max_cap)

        source_factor = 100.0 if quote and quote.is_realtime and not quote.degraded_reason else 55.0
        forecast_conf = sum(forecast_confidences) / len(forecast_confidences) if forecast_confidences else 25.0
        confidence = 0.5 * data_quality + 0.25 * forecast_conf + 0.25 * source_factor
        required_horizons = {1, 5, 20}
        fully_calibrated = required_horizons.issubset(forecasts) and all(
            forecasts[horizon].calibration_status == "calibrated" for horizon in required_horizons
        )
        confidence = clamp(confidence, 0, 85 if fully_calibrated else 60)
        if not preflight.ok:
            score = min(score, 45)
            confidence = min(confidence, 30)
            raw_target = current_weight if current_weight > 0 else 0

        return CandidateSignal(
            instrument=instrument,
            indicator=indicator,
            quote=quote,
            forecasts=forecasts,
            holding=holding,
            current_weight=current_weight,
            score=round(clamp(score, 0, 100), 2),
            confidence=round(confidence, 2),
            data_quality=data_quality,
            reasons=list(dict.fromkeys(reasons))[:10],
            risks=list(dict.fromkeys(risks))[:12],
            theme_score=theme_score,
            fund_quality_score=quality_score,
            raw_target_weight=raw_target,
            actionable=(
                preflight.ok
                and bool(quote and quote.is_realtime and quote.source != "mock" and not quote.degraded_reason)
                and self.calendar.actionable_day(now.date())
                and self.clock.price_session_open(now, is_trade_day=True)
            ),
        )

    def _apply_portfolio_constraints(
        self,
        candidates: list[CandidateSignal],
        exposure_cap: float,
    ) -> None:
        theme_cap = float(self.strategy["signal"]["single_theme_target_cap"])
        step_cap = float(self.strategy["signal"]["one_step_adjustment_cap"])
        allocated_by_theme: dict[str, float] = defaultdict(float)
        allocated_total = 0.0
        for item in sorted(candidates, key=lambda value: value.score, reverse=True):
            theme = item.instrument.theme_l1 or "未分类"
            remaining_theme = max(0.0, theme_cap - allocated_by_theme[theme])
            remaining_total = max(0.0, exposure_cap - allocated_total)
            strategic = min(item.raw_target_weight, remaining_theme, remaining_total)
            allocated_by_theme[theme] += strategic
            allocated_total += strategic
            item.target_weight = round(strategic, 4)
            lower = max(0.0, item.current_weight - step_cap)
            upper = min(1.0, item.current_weight + step_cap)
            item.first_step_target_weight = round(min(upper, max(lower, strategic)), 4)

    def _label_state(self, item: CandidateSignal) -> None:
        cfg = self.strategy["signal"]
        if item.data_quality < float(cfg["minimum_data_quality"]) or any(
            risk.startswith("核心数据缺失") for risk in item.risks
        ):
            item.state = "数据异常"
            item.actionable = False
            return
        diff = item.first_step_target_weight - item.current_weight
        if item.current_weight > 0:
            if item.score <= float(cfg["hard_reduce_score"]) or diff <= -float(cfg["reduce_threshold_weight_points"]):
                item.state = "减仓"
            elif diff >= float(cfg["add_threshold_weight_points"]):
                item.state = "加仓"
            elif diff >= float(cfg["small_add_threshold_weight_points"]):
                item.state = "小幅加仓"
            elif item.score < float(cfg["reduce_score"]):
                item.state = "风险观察"
            else:
                item.state = "持有"
        else:
            one_day = item.forecasts.get(1)
            p_up = float(one_day.p_up) if one_day and one_day.p_up is not None else 0.5
            if item.score >= float(cfg["entry_score"]) and p_up >= 0.55:
                item.state = "可入场"
            elif item.score >= float(cfg["probe_score"]):
                item.state = "可试探"
            else:
                item.state = "观察"
        if not item.actionable and item.state in {"加仓", "小幅加仓", "减仓", "可入场", "可试探"}:
            item.risks.append("数据链路尚未达到执行级，只作为研究信号展示")

    def _apply_state_hysteresis(
        self,
        item: CandidateSignal,
        previous: SignalSnapshot | None,
        now: datetime,
    ) -> None:
        if previous is None or item.state == "数据异常":
            return
        previous_time = previous.as_of_time
        if previous_time.tzinfo is None:
            previous_time = previous_time.replace(tzinfo=self.settings.timezone)
        min_minutes = float(self.strategy["signal"].get("state_min_hold_minutes", 30))
        score_delta = float(self.strategy["signal"].get("state_change_score_delta", 5))
        if now - previous_time > timedelta(minutes=min_minutes):
            return
        if item.state == previous.state:
            return
        # Hard risk deterioration is never delayed. All other small oscillations
        # are filtered so a 10–15 minute signal schedule does not chatter.
        hard_risk = item.score <= float(self.strategy["signal"]["hard_reduce_score"])
        if not hard_risk and abs(item.score - float(previous.score)) < score_delta:
            item.state = previous.state
            item.reasons.append(f"迟滞过滤：{int(min_minutes)} 分钟内分数变化不足 {score_delta:g}")
            item.reasons = list(dict.fromkeys(item.reasons))[:10]

    def refresh_all(self, db: Session, run_id: str | None = None) -> dict:
        run_id = run_id or uuid4().hex
        now = datetime.now(self.settings.timezone)
        instruments = db.scalars(select(Instrument).where(Instrument.enabled.is_(True))).all()
        holdings = {item.instrument_id: item for item in db.scalars(select(Holding)).all()}

        latest_quotes: dict[int, QuoteSnapshot] = {}
        latest_indicators: dict[int, IndicatorSnapshot] = {}
        latest_forecasts: dict[int, dict[int, ForecastSnapshot]] = {}
        previous_signals: dict[int, SignalSnapshot] = {}
        for instrument in instruments:
            quote = db.scalar(
                select(QuoteSnapshot)
                .where(QuoteSnapshot.instrument_id == instrument.id)
                .order_by(QuoteSnapshot.quote_time.desc())
                .limit(1)
            )
            if quote:
                latest_quotes[instrument.id] = quote
            indicator = db.scalar(
                select(IndicatorSnapshot)
                .where(IndicatorSnapshot.instrument_id == instrument.id)
                .order_by(IndicatorSnapshot.as_of_date.desc(), IndicatorSnapshot.generated_at.desc())
                .limit(1)
            )
            if indicator:
                latest_indicators[instrument.id] = indicator
            forecasts = db.scalars(
                select(ForecastSnapshot)
                .where(ForecastSnapshot.instrument_id == instrument.id)
                .order_by(ForecastSnapshot.as_of_date.desc(), ForecastSnapshot.generated_at.desc())
            ).all()
            latest_forecasts[instrument.id] = self._latest_by_horizon(list(forecasts))
            previous = db.scalar(
                select(SignalSnapshot)
                .where(SignalSnapshot.instrument_id == instrument.id)
                .order_by(SignalSnapshot.as_of_time.desc())
                .limit(1)
            )
            if previous:
                previous_signals[instrument.id] = previous

        weights = self._portfolio_weights(db, latest_quotes)
        candidates = [
            self._build_candidate(
                db,
                instrument,
                latest_quotes.get(instrument.id),
                latest_indicators.get(instrument.id),
                latest_forecasts.get(instrument.id, {}),
                holdings.get(instrument.id),
                weights.get(instrument.id, 0.0),
                now,
            )
            for instrument in instruments
        ]
        market_regime, exposure_cap, regime_evidence = self._market_regime(
            list(instruments), latest_indicators
        )
        self._apply_portfolio_constraints(candidates, exposure_cap)
        for item in candidates:
            self._label_state(item)
            self._apply_state_hysteresis(item, previous_signals.get(item.instrument.id), now)

        strategy_version = self.strategy["version"]
        indicator_version = self.strategy["indicator_version"]
        forecast_version = self.strategy["forecast_version"]
        created = 0
        state_counts: dict[str, int] = defaultdict(int)
        for item in candidates:
            input_payload = {
                "indicator": item.indicator.input_hash if item.indicator else None,
                "quote": item.quote.quality_hash if item.quote else None,
                "forecasts": {key: value.input_hash for key, value in item.forecasts.items()},
                "holding": {
                    "shares": str(item.holding.shares),
                    "cost": str(item.holding.cost_price),
                }
                if item.holding
                else None,
                "strategy": self.strategy,
            }
            evidence = {
                "theme_score": item.theme_score,
                "fund_quality_score": item.fund_quality_score,
                "current_weight": round(item.current_weight, 4),
                "market_regime": market_regime,
                "portfolio_exposure_cap": exposure_cap,
                "regime_evidence": regime_evidence,
                "quote_source": item.quote.source if item.quote else None,
                "quote_realtime": item.quote.is_realtime if item.quote else False,
                "forecasts": {
                    horizon: {
                        "p_up": value.p_up,
                        "expected_return": value.expected_return,
                        "q10": value.q10,
                        "q50": value.q50,
                        "q90": value.q90,
                        "sample_count": value.sample_count,
                        "confidence": value.confidence,
                        "calibration_status": value.calibration_status,
                    }
                    for horizon, value in item.forecasts.items()
                },
            }
            snapshot = SignalSnapshot(
                instrument_id=item.instrument.id,
                as_of_time=now,
                strategy_version=strategy_version,
                indicator_version=indicator_version,
                forecast_version=forecast_version,
                state=item.state,
                score=item.score,
                confidence=item.confidence,
                target_weight=item.target_weight,
                first_step_target_weight=item.first_step_target_weight,
                reasons_json=item.reasons,
                risks_json=item.risks,
                evidence_json=evidence,
                input_hash=stable_hash(input_payload),
                expires_at=now + timedelta(minutes=max(20, int(self.strategy["intervals"]["signal_minutes"]) * 2)),
                is_actionable=item.actionable,
                data_quality=item.data_quality,
            )
            db.add(snapshot)
            created += 1
            state_counts[item.state] += 1
        db.flush()
        emit_event(
            db,
            "signals.updated",
            {
                "run_id": run_id,
                "created": created,
                "state_counts": dict(state_counts),
                "market_regime": market_regime,
                "exposure_cap": exposure_cap,
            },
        )
        return {
            "run_id": run_id,
            "created": created,
            "state_counts": dict(state_counts),
            "market_regime": market_regime,
            "exposure_cap": exposure_cap,
        }
