from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import ForecastSnapshot, Holding, IndicatorSnapshot, Instrument, QuoteSnapshot
from app.services.signal_service import CandidateSignal, SignalService


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
        holding: Holding | None,
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
        return item
