from __future__ import annotations

from uuid import uuid4

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import DailyBar, IndicatorSnapshot, Instrument
from app.services.event_service import emit_event
from app.utils.hashing import stable_hash
from app.utils.indicators import calculate_indicators


class IndicatorService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.strategy = self.settings.load_strategy()

    def refresh_all(self, db: Session, run_id: str | None = None) -> dict:
        run_id = run_id or uuid4().hex
        instruments = db.scalars(select(Instrument).where(Instrument.enabled.is_(True))).all()
        created = 0
        skipped = 0
        failures: list[dict] = []
        version = self.strategy["indicator_version"]
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
                [{"date": row.trade_date, "hash": row.quality_hash} for row in rows[-300:]]
            )
            try:
                result = calculate_indicators(frame, self.strategy["indicator"])
            except Exception as exc:
                failures.append({"ts_code": instrument.ts_code, "reason": f"{type(exc).__name__}: {exc}"})
                continue
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
                    values_json=result.values,
                    technical_score=result.technical_score,
                    risk_score=result.risk_score,
                    trend_label=result.trend_label,
                    data_quality=result.data_quality,
                    input_hash=input_hash,
                )
                db.add(snapshot)
                created += 1
            else:
                snapshot.values_json = result.values
                snapshot.technical_score = result.technical_score
                snapshot.risk_score = result.risk_score
                snapshot.trend_label = result.trend_label
                snapshot.data_quality = result.data_quality
                snapshot.input_hash = input_hash
        db.flush()
        emit_event(
            db,
            "indicators.updated",
            {"run_id": run_id, "created": created, "skipped": skipped, "failures": failures},
        )
        return {"run_id": run_id, "created": created, "skipped": skipped, "failures": failures}
