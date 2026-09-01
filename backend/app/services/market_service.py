from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import DailyBar, Instrument, QuoteSnapshot, SectorSnapshot
from app.providers.base import MarketProvider, ProviderError
from app.services.audit_service import AuditTimer, record_provider_audit
from app.services.event_service import emit_event
from app.utils.hashing import stable_hash

logger = logging.getLogger(__name__)


class MarketService:
    def __init__(
        self,
        provider: MarketProvider,
        settings: Settings | None = None,
        *,
        persist_provider_audits: bool = True,
    ) -> None:
        self.provider = provider
        self.settings = settings or get_settings()
        self.persist_provider_audits = persist_provider_audits

    @staticmethod
    def _qualify_quote_timestamp(item, fetched_at: datetime) -> tuple[bool, str | None]:
        source_time = item.quote_time
        if source_time.tzinfo is None:
            source_time = source_time.replace(tzinfo=fetched_at.tzinfo)
        age = fetched_at - source_time
        source = str(item.source or "").lower()
        provider_timestamp_capable = source.startswith("tushare:") and "fund_daily" not in source
        verified = bool(
            item.is_realtime
            and provider_timestamp_capable
            and source_time.date() == fetched_at.date()
            and timedelta(minutes=-5) <= age <= timedelta(minutes=20)
        )
        if verified:
            return True, None
        if not item.is_realtime:
            return False, item.degraded_reason or "provider marked quote non-realtime"
        if not provider_timestamp_capable:
            return False, "quote source timestamp has not completed provider qualification"
        if source_time.date() != fetched_at.date():
            return False, "quote source date is not today"
        return False, "quote source timestamp is stale or future-dated"

    def sync_instruments(self, db: Session, codes: list[str] | None = None, run_id: str | None = None) -> dict:
        run_id = run_id or uuid4().hex
        timer = AuditTimer()
        error: Exception | None = None
        records = []
        try:
            records = self.provider.list_instruments(codes)
        except Exception as exc:
            error = exc
            raise
        finally:
            if self.persist_provider_audits:
                record_provider_audit(
                    db,
                    run_id=run_id,
                    operation="list_instruments",
                    provider=self.provider,
                    result=records,
                    error=error,
                    latency_ms=timer.elapsed_ms,
                )
        created = 0
        updated = 0
        for item in records:
            row = db.scalar(select(Instrument).where(Instrument.ts_code == item.ts_code))
            if row is None:
                row = Instrument(ts_code=item.ts_code, symbol=item.symbol, name=item.name)
                db.add(row)
                created += 1
            else:
                updated += 1
            row.symbol = item.symbol
            row.name = item.name
            row.kind = item.kind
            row.exchange = item.exchange
            row.theme_l1 = item.theme_l1
            row.theme_l2 = item.theme_l2
            row.benchmark = item.benchmark
            row.enabled = item.enabled
            row.metadata_json = item.metadata
        db.flush()
        emit_event(db, "instruments.updated", {"created": created, "updated": updated, "run_id": run_id})
        return {"run_id": run_id, "created": created, "updated": updated, "total": len(records)}

    def refresh_daily_bars(
        self,
        db: Session,
        lookback_days: int = 900,
        codes: list[str] | None = None,
        run_id: str | None = None,
    ) -> dict:
        run_id = run_id or uuid4().hex
        instruments = db.scalars(
            select(Instrument).where(Instrument.enabled.is_(True)).order_by(Instrument.ts_code)
        ).all()
        if codes:
            wanted = {code.upper() for code in codes}
            instruments = [item for item in instruments if item.ts_code.upper() in wanted or item.symbol in wanted]
        end_date = datetime.now(self.settings.timezone).date()
        totals = {"inserted": 0, "updated": 0, "instruments": 0, "failures": []}
        for instrument in instruments:
            start_date = end_date - timedelta(days=lookback_days)
            earliest = db.scalar(
                select(func.min(DailyBar.trade_date)).where(DailyBar.instrument_id == instrument.id)
            )
            latest = db.scalar(
                select(func.max(DailyBar.trade_date)).where(DailyBar.instrument_id == instrument.id)
            )
            if earliest is not None and latest is not None and earliest <= start_date:
                # History already covers the requested lookback; refresh a short overlap only.
                start_date = max(start_date, latest - timedelta(days=7))
            timer = AuditTimer()
            error: Exception | None = None
            records = []
            try:
                records = self.provider.fetch_daily_bars(instrument.ts_code, start_date, end_date)
                totals["instruments"] += 1
                for item in records:
                    row = db.scalar(
                        select(DailyBar).where(
                            DailyBar.instrument_id == instrument.id,
                            DailyBar.trade_date == item.trade_date,
                            DailyBar.adjust == item.adjust,
                        )
                    )
                    payload = item.to_dict()
                    if row is None:
                        row = DailyBar(
                            instrument_id=instrument.id,
                            trade_date=item.trade_date,
                            open=item.open,
                            high=item.high,
                            low=item.low,
                            close=item.close,
                            adjust=item.adjust,
                            source=item.source,
                            quality_hash=stable_hash(payload),
                        )
                        db.add(row)
                        totals["inserted"] += 1
                    else:
                        totals["updated"] += 1
                    row.open = item.open
                    row.high = item.high
                    row.low = item.low
                    row.close = item.close
                    row.pre_close = item.pre_close
                    row.volume = item.volume
                    row.amount = item.amount
                    row.pct_change = item.pct_change
                    row.source = item.source
                    row.quality_hash = stable_hash(payload)
            except Exception as exc:
                error = exc
                totals["failures"].append({"ts_code": instrument.ts_code, "error": f"{type(exc).__name__}: {exc}"})
            finally:
                if self.persist_provider_audits:
                    record_provider_audit(
                        db,
                        run_id=run_id,
                        operation="fetch_daily_bars",
                        provider=self.provider,
                        result=records,
                        error=error,
                        latency_ms=timer.elapsed_ms,
                    )
        db.flush()
        emit_event(db, "bars.updated", {**totals, "run_id": run_id})
        return {"run_id": run_id, **totals}

    def refresh_quotes(
        self,
        db: Session,
        codes: list[str] | None = None,
        run_id: str | None = None,
    ) -> dict:
        run_id = run_id or uuid4().hex
        instruments = db.scalars(
            select(Instrument).where(Instrument.enabled.is_(True)).order_by(Instrument.ts_code)
        ).all()
        if codes:
            wanted = {code.upper() for code in codes}
            instruments = [item for item in instruments if item.ts_code.upper() in wanted or item.symbol in wanted]
        by_code = {item.ts_code: item for item in instruments}
        timer = AuditTimer()
        error: Exception | None = None
        records = []
        try:
            records = self.provider.fetch_spot_quotes(list(by_code))
        except Exception as exc:
            error = exc
            raise
        finally:
            if self.persist_provider_audits:
                record_provider_audit(
                    db,
                    run_id=run_id,
                    operation="fetch_spot_quotes",
                    provider=self.provider,
                    result=records,
                    error=error,
                    latency_ms=timer.elapsed_ms,
                )
        inserted = 0
        realtime = 0
        raw_realtime = 0
        degraded = 0
        fetched_at = datetime.now(self.settings.timezone)
        for item in records:
            instrument = by_code.get(item.ts_code)
            if not instrument:
                continue
            timestamp_verified, timestamp_reason = self._qualify_quote_timestamp(item, fetched_at)
            effective_realtime = bool(item.is_realtime and timestamp_verified and not item.degraded_reason)
            effective_degraded_reason = item.degraded_reason or timestamp_reason
            db.add(
                QuoteSnapshot(
                    instrument_id=instrument.id,
                    quote_time=item.quote_time,
                    fetched_at=fetched_at,
                    timestamp_verified=timestamp_verified,
                    price=item.price,
                    open=item.open,
                    high=item.high,
                    low=item.low,
                    pre_close=item.pre_close,
                    pct_change=item.pct_change,
                    volume=item.volume,
                    amount=item.amount,
                    premium_rate=item.premium_rate,
                    source=item.source,
                    is_realtime=effective_realtime,
                    degraded_reason=effective_degraded_reason,
                    quality_hash=stable_hash(item.to_dict()),
                )
            )
            inserted += 1
            raw_realtime += int(item.is_realtime)
            realtime += int(effective_realtime)
            degraded += int(bool(effective_degraded_reason))
        db.flush()
        emit_event(
            db,
            "quotes.updated",
            {
                "inserted": inserted,
                "realtime": realtime,
                "raw_realtime": raw_realtime,
                "degraded": degraded,
                "run_id": run_id,
            },
        )
        return {
            "run_id": run_id,
            "inserted": inserted,
            "realtime": realtime,
            "raw_realtime": raw_realtime,
            "degraded": degraded,
        }

    def purge_old_quotes(self, db: Session, keep_days: int = 45) -> int:
        cutoff = datetime.now(self.settings.timezone) - timedelta(days=keep_days)
        result = db.execute(delete(QuoteSnapshot).where(QuoteSnapshot.quote_time < cutoff))
        return int(result.rowcount or 0)

    def refresh_sector_snapshots(self, db: Session, run_id: str | None = None) -> dict:
        """回填行业板块涨跌家数快照（K线企稳看板用）。

        AKShare 板块接口不可达时（如网络受限）返回 inserted=0 + error，不抛出
        阻断主流程；由调用方决定板块列显示 "—"。
        """
        run_id = run_id or uuid4().hex
        timer = AuditTimer()
        error: Exception | None = None
        records = []
        try:
            if not hasattr(self.provider, "fetch_sector_snapshots"):
                raise ProviderError("provider 不支持板块快照")
            records = self.provider.fetch_sector_snapshots()
        except Exception as exc:
            error = exc
            logger.warning("sector snapshot refresh failed (degraded to empty): %s", exc)
        finally:
            if self.persist_provider_audits:
                record_provider_audit(
                    db,
                    run_id=run_id,
                    operation="fetch_sector_snapshots",
                    provider=self.provider,
                    result=records,
                    error=error,
                    latency_ms=timer.elapsed_ms,
                )
        if error:
            emit_event(
                db,
                "sector_snapshots.failed",
                {"run_id": run_id, "error": type(error).__name__},
            )
            return {"run_id": run_id, "inserted": 0, "error": type(error).__name__}

        inserted = 0
        for item in records:
            existing = db.scalar(
                select(SectorSnapshot).where(
                    SectorSnapshot.sector_name == item.sector_name,
                    SectorSnapshot.trade_date == item.trade_date,
                    SectorSnapshot.source == item.source,
                )
            )
            if existing:
                existing.up_count = item.up_count
                existing.down_count = item.down_count
                existing.flat_count = item.flat_count
                existing.total_count = item.total_count
                existing.pct_change = item.pct_change
                existing.fetched_at = datetime.now(self.settings.timezone)
                existing.quality_hash = stable_hash(item.to_dict())
            else:
                db.add(
                    SectorSnapshot(
                        sector_name=item.sector_name,
                        trade_date=item.trade_date,
                        up_count=item.up_count,
                        down_count=item.down_count,
                        flat_count=item.flat_count,
                        total_count=item.total_count,
                        pct_change=item.pct_change,
                        source=item.source,
                        fetched_at=datetime.now(self.settings.timezone),
                        quality_hash=stable_hash(item.to_dict()),
                    )
                )
            inserted += 1
        db.flush()
        emit_event(
            db,
            "sector_snapshots.updated",
            {"inserted": inserted, "run_id": run_id},
        )
        return {"run_id": run_id, "inserted": inserted, "error": None}
