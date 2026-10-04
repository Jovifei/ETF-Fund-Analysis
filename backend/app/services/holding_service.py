from __future__ import annotations

from decimal import Decimal
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import Holding, Instrument, QuoteSnapshot
from app.services.event_service import emit_event
from app.services.snapshot_contract import quote_issues


class HoldingNotFoundError(LookupError):
    pass


class HoldingService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @staticmethod
    def _instrument(db: Session, ts_code: str) -> Instrument:
        instrument = db.scalar(select(Instrument).where(Instrument.ts_code == ts_code.upper()))
        if instrument is None:
            raise HoldingNotFoundError(f"未找到标的 {ts_code}")
        return instrument

    def list(self, db: Session, *, user_id: int | None = None) -> list[dict]:
        holdings = db.scalars(select(Holding).where(Holding.user_id == user_id).order_by(Holding.id)).all()
        result: list[dict] = []
        for holding in holdings:
            instrument = db.get(Instrument, holding.instrument_id)
            quote = db.scalar(
                select(QuoteSnapshot)
                .where(QuoteSnapshot.instrument_id == holding.instrument_id)
                .order_by(QuoteSnapshot.quote_time.desc())
                .limit(1)
            )
            reference = datetime.now(self.settings.timezone)
            quote_problems = quote_issues(quote, self.settings, at=reference)
            current_quote = quote if not quote_problems else None
            shares = float(holding.shares or 0)
            cost = float(holding.cost_price or 0)
            price = float(current_quote.price) if current_quote is not None else None
            market_value = shares * price if price is not None else None
            cost_value = shares * cost
            pnl = market_value - cost_value if market_value is not None else None
            result.append(
                {
                    "id": holding.id,
                    "ts_code": instrument.ts_code if instrument else None,
                    "name": instrument.name if instrument else None,
                    "theme_l1": instrument.theme_l1 if instrument else None,
                    "theme_l2": instrument.theme_l2 if instrument else None,
                    "shares": shares,
                    "cost_price": cost,
                    "latest_price": price,
                    "market_value": round(market_value, 2) if market_value is not None else None,
                    "pnl": round(pnl, 2) if pnl is not None else None,
                    "pnl_pct": round((price / cost - 1) * 100, 3) if price is not None and cost > 0 else None,
                    "quote_issues": quote_problems,
                    "target_weight": holding.target_weight,
                    "notes": holding.notes,
                    "updated_at": holding.updated_at,
                }
            )
        pricing_complete = all(item["market_value"] is not None for item in result)
        total = (
            sum(float(item["market_value"]) for item in result)
            if pricing_complete
            else 0.0
        )
        for item in result:
            item["current_weight"] = (
                round(float(item["market_value"]) / total, 6)
                if pricing_complete and total > 0 and item["market_value"] is not None
                else None
            )
            item["pricing_complete"] = pricing_complete
        return result

    def upsert(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        ts_code: str,
        shares: float,
        cost_price: float,
        target_weight: float | None = None,
        notes: str | None = None,
    ) -> Holding:
        instrument = self._instrument(db, ts_code)
        holding = db.scalar(select(Holding).where(Holding.user_id == user_id, Holding.instrument_id == instrument.id))
        if holding is None:
            holding = Holding(user_id=user_id, instrument_id=instrument.id)
            db.add(holding)
        holding.shares = Decimal(str(max(0.0, shares)))
        holding.cost_price = Decimal(str(max(0.0, cost_price)))
        holding.target_weight = target_weight
        holding.notes = notes
        db.flush()
        emit_event(
            db,
            "holdings.updated",
            {"ts_code": instrument.ts_code, "action": "upsert", "user_id": user_id},
        )
        return holding

    def delete(self, db: Session, ts_code: str, *, user_id: int | None = None) -> bool:
        instrument = self._instrument(db, ts_code)
        holding = db.scalar(select(Holding).where(Holding.user_id == user_id, Holding.instrument_id == instrument.id))
        if holding is None:
            return False
        db.delete(holding)
        db.flush()
        emit_event(
            db,
            "holdings.updated",
            {"ts_code": instrument.ts_code, "action": "delete", "user_id": user_id},
        )
        return True
