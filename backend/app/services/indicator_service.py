from __future__ import annotations

from uuid import uuid4

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import DailyBar, IndicatorSnapshot, Instrument
from app.services.event_service import emit_event
from app.services.strategy_engine import evaluate_strategy_families
from app.utils.feature_store import FEATURE_SCHEMA_VERSION
from app.utils.hashing import stable_hash
from app.utils.reproducibility import reproducibility_payload
from app.utils.indicators_v05 import IndicatorResult, calculate_indicators
from app.utils.numbers import clamp


class IndicatorService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.strategy = self.settings.load_strategy()

    @staticmethod
    def _trend_label(score: float) -> str:
        if score >= 72:
            return "强势"
        if score >= 58:
            return "偏强"
        if score >= 43:
            return "震荡"
        if score >= 30:
            return "偏弱"
        return "弱势"

    @staticmethod
    def _rps(results: dict[int, IndicatorResult], key: str) -> dict[int, float]:
        values = {
            instrument_id: result.values.get(key)
            for instrument_id, result in results.items()
            if result.values.get(key) is not None
        }
        if len(values) < 3:
            return {instrument_id: 50.0 for instrument_id in results}
        series = pd.Series(values, dtype=float)
        ranks = series.rank(method="average", pct=True) * 100
        return {instrument_id: round(float(ranks.get(instrument_id, 50.0)), 2) for instrument_id in results}

    def refresh_all(self, db: Session, run_id: str | None = None) -> dict:
        run_id = run_id or uuid4().hex
        instruments = db.scalars(select(Instrument).where(Instrument.enabled.is_(True))).all()
        skipped = 0
        failures: list[dict] = []
        computed: dict[int, IndicatorResult] = {}
        metadata: dict[int, tuple[Instrument, list[DailyBar], str]] = {}
        for instrument in instruments:
            rows = db.scalars(
                select(DailyBar)
                .where(DailyBar.instrument_id == instrument.id)
                .order_by(DailyBar.trade_date)
            ).all()
            if len(rows) < 30:
                skipped += 1
                failures.append({"ts_code": instrument.ts_code, "reason": "历史 K 线不足 30 根"})
                continue
            frame = pd.DataFrame(
                [
                    {
                        "trade_date": row.trade_date,
                        "open": row.open,
                        "high": row.high,
                        "low": row.low,
                        "close": row.close,
                        "volume": row.volume or 0,
                        "amount": row.amount or 0,
                    }
                    for row in rows
                ]
            )
            input_hash = stable_hash(
                [{"date": row.trade_date, "hash": row.quality_hash} for row in rows[-400:]]
            )
            try:
                result = calculate_indicators(frame, self.strategy["indicator"])
            except Exception as exc:
                failures.append({"ts_code": instrument.ts_code, "reason": f"{type(exc).__name__}: {exc}"})
                continue
            computed[instrument.id] = result
            metadata[instrument.id] = (instrument, list(rows), input_hash)

        rps20 = self._rps(computed, "return_20d")
        rps60 = self._rps(computed, "return_60d")
        rps120 = self._rps(computed, "return_120d")
        created = 0
        version = self.strategy["indicator_version"]
        feature_schema_version = self.strategy.get("feature_schema_version", FEATURE_SCHEMA_VERSION)
        strategy_cfg = self.strategy.get("strategy_engine", {})
        for instrument_id, result in computed.items():
            instrument, rows, input_hash = metadata[instrument_id]
            values = dict(result.values)
            values["rps20"] = rps20[instrument_id]
            values["rps60"] = rps60[instrument_id]
            values["rps120"] = rps120[instrument_id]
            evaluation = evaluate_strategy_families(values, strategy_cfg)
            base_score = float(result.technical_score)
            technical_score = round(clamp(base_score * 0.25 + evaluation.composite_score * 0.75, 0, 100), 2)
            adjusted_risk = round(clamp(result.risk_score + min(12, 4 * len(evaluation.risks)), 0, 100), 2)
            values["base_technical_score"] = round(base_score, 2)
            values["strategy_composite_score"] = evaluation.composite_score
            values["strategy_family_scores"] = evaluation.family_scores
            values["strategy_signals"] = evaluation.signals
            values["strategy_risks"] = evaluation.risks
            values["technical_reasons"] = list(
                dict.fromkeys(list(values.get("technical_reasons") or []) + evaluation.reasons)
            )[:16]
            values["indicator_version"] = version
            reproducibility = reproducibility_payload(
                strategy=self.strategy,
                feature_schema_version=feature_schema_version,
                features=values.keys(),
                code_component="IndicatorService.v0.7",
            )
            values["reproducibility"] = reproducibility

            as_of_date = rows[-1].trade_date
            snapshot = db.scalar(
                select(IndicatorSnapshot).where(
                    IndicatorSnapshot.instrument_id == instrument.id,
                    IndicatorSnapshot.as_of_date == as_of_date,
                    IndicatorSnapshot.version == version,
                )
            )
            if snapshot is None:
                snapshot = IndicatorSnapshot(
                    instrument_id=instrument.id,
                    as_of_date=as_of_date,
                    version=version,
                    values_json=values,
                    technical_score=technical_score,
                    risk_score=adjusted_risk,
                    trend_label=self._trend_label(technical_score),
                    data_quality=result.data_quality,
                    input_hash=input_hash,
                    feature_schema_version=feature_schema_version,
                    config_hash=reproducibility["config_hash"],
                    git_commit_sha=reproducibility["git_commit_sha"],
                    reproducibility_json=reproducibility,
                )
                db.add(snapshot)
                created += 1
            else:
                snapshot.values_json = values
                snapshot.technical_score = technical_score
                snapshot.risk_score = adjusted_risk
                snapshot.trend_label = self._trend_label(technical_score)
                snapshot.data_quality = result.data_quality
                snapshot.input_hash = input_hash
                snapshot.feature_schema_version = feature_schema_version
                snapshot.config_hash = reproducibility["config_hash"]
                snapshot.git_commit_sha = reproducibility["git_commit_sha"]
                snapshot.reproducibility_json = reproducibility
        db.flush()
        emit_event(
            db,
            "indicators.updated",
            {
                "run_id": run_id,
                "created": created,
                "updated": max(0, len(computed) - created),
                "skipped": skipped,
                "failures": failures,
                "indicator_version": version,
            },
        )
        return {
            "run_id": run_id,
            "created": created,
            "updated": max(0, len(computed) - created),
            "skipped": skipped,
            "failures": failures,
            "indicator_version": version,
        }
