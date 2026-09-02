from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import ForecastSnapshot, IndicatorSnapshot, Instrument, QuoteSnapshot
from app.services.signal_service import CandidateSignal, SignalService
from app.utils.numbers import clamp


class SignalV05Service(SignalService):
    """v0.5 market gate and strategy-family evidence layered on the v0.4 state machine."""

    def _market_regime(
        self,
        instruments: list[Instrument],
        indicators: dict[int, IndicatorSnapshot],
    ) -> tuple[str, float, dict]:
        label, cap, evidence = super()._market_regime(instruments, indicators)
        benchmark_code = str(self.strategy["signal"].get("regime_benchmark", "510300.SH")).upper()
        benchmark = next((item for item in instruments if item.ts_code.upper() == benchmark_code), None)
        indicator = indicators.get(benchmark.id) if benchmark else None
        if indicator is None:
            return label, cap, evidence
        values = indicator.values_json or {}
        rsrs_z = float(values.get("rsrs_zscore") or 0)
        adx = float(values.get("adx14") or 0)
        plus_di = float(values.get("plus_di14") or 0)
        minus_di = float(values.get("minus_di14") or 0)
        bearish = adx >= 25 and minus_di > plus_di
        caps = self.strategy["signal"].get("portfolio_exposure_caps", {})
        if rsrs_z <= -1.2:
            label = "extreme_risk"
        elif rsrs_z <= -0.7 or bearish:
            label = "high_risk"
        elif label == "low_risk" and rsrs_z < -0.2:
            label = "normal"
        cap = float(caps.get(label, cap))
        evidence.update({
            "rsrs_zscore": round(rsrs_z, 4),
            "adx14": round(adx, 2),
            "dmi_direction": "bullish" if plus_di > minus_di else "bearish",
        })
        return label, cap, evidence

    def _build_candidate(
        self,
        db: Session,
        instrument: Instrument,
        quote: QuoteSnapshot | None,
        indicator: IndicatorSnapshot | None,
        forecasts: dict[int, ForecastSnapshot],
        holding: object | None,
        current_weight: float,
        now: datetime,
    ) -> CandidateSignal:
        item = super()._build_candidate(db, instrument, quote, indicator, forecasts, holding, current_weight, now)
        if not indicator:
            return item
        values = indicator.values_json or {}
        strategy_hits = values.get("strategy_signals") or []
        positive = [str(hit.get("name")) for hit in strategy_hits if hit.get("direction") == "positive" and hit.get("name")]
        if positive:
            item.reasons = list(dict.fromkeys(item.reasons + ["策略共振：" + "、".join(positive[:4])]))[:12]
        item.risks = list(dict.fromkeys(item.risks + list(values.get("strategy_risks") or [])))[:12]
        adjustment_cfg = self.strategy.get("signal", {}).get("forecast_risk_adjustment", {})
        calibrated_forecasts = [
            item for item in forecasts.values()
            if item.calibration_status == "calibrated"
        ]
        if bool(adjustment_cfg.get("enabled", False)) and calibrated_forecasts:
            contributions: list[float] = []
            for horizon, weight in ((1, 0.50), (5, 0.30), (20, 0.20)):
                forecast = forecasts.get(horizon)
                if forecast is None or forecast.expected_return is None:
                    continue
                probability = float(forecast.p_up if forecast.p_up is not None else 0.5)
                expected_scale = float(adjustment_cfg.get("expected_return_scale", 0.04))
                downside_scale = float(adjustment_cfg.get("downside_scale", 0.06))
                probability_component = (probability - 0.5) * 2.0
                expected_component = clamp(float(forecast.expected_return) / expected_scale, -1.0, 1.0)
                downside = float(forecast.q10 if forecast.q10 is not None else 0.0)
                downside_component = clamp(downside / downside_scale, -1.0, 1.0)
                combined = (
                    probability_component * float(adjustment_cfg.get("probability_weight", 0.45))
                    + expected_component * float(adjustment_cfg.get("expected_return_weight", 0.35))
                    + downside_component * float(adjustment_cfg.get("downside_weight", 0.20))
                )
                contributions.append(combined * weight)
            if contributions:
                maximum = float(adjustment_cfg.get("maximum_points", 4.0))
                adjustment = clamp(sum(contributions) * maximum, -maximum, maximum)
                item.score = round(clamp(item.score + adjustment, 0.0, 100.0), 2)
                item.reasons = list(dict.fromkeys(item.reasons + [f"预测收益/下行风险调整 {adjustment:+.2f} 分"]))[:12]
        return item
