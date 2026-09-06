from __future__ import annotations

import logging
import math
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
        totals = {"inserted": 0, "updated": 0, "unchanged": 0, "instruments": 0, "failures": []}
        for instrument in instruments:
            start_date = end_date - timedelta(days=lookback_days)
            earliest, latest = db.execute(
                select(func.min(DailyBar.trade_date), func.max(DailyBar.trade_date))
                .where(DailyBar.instrument_id == instrument.id)
            ).one()
            if earliest is not None and latest is not None and earliest <= start_date:
                # Keep a correction overlap; extending history still backfills.
                start_date = max(start_date, latest - timedelta(days=7))
            timer = AuditTimer()
            error: Exception | None = None
            records = []
            try:
                records = list(self.provider.fetch_daily_bars(instrument.ts_code, start_date, end_date))
                # Validate the complete batch before touching persisted history.
                # Exact duplicates are idempotent; conflicting duplicates are
                # not silently selected by whichever record happens to be last.
                batch = self._validated_bar_batch(records, instrument.ts_code, start_date, end_date)
                counts = {"inserted": 0, "updated": 0, "unchanged": 0}
                with db.begin_nested():
                    existing = {
                        (row.trade_date, row.adjust): row
                        for row in db.scalars(select(DailyBar).where(
                            DailyBar.instrument_id == instrument.id,
                            DailyBar.trade_date >= start_date, DailyBar.trade_date <= end_date,
                        ))
                    }
                    for key, (item, content_hash) in batch.items():
                        row = existing.get(key)
                        if row is not None and row.quality_hash == content_hash:
                            counts["unchanged"] += 1
                            continue
                        if row is None:
                            row = DailyBar(instrument_id=instrument.id, trade_date=item.trade_date,
                                           adjust=item.adjust)
                            db.add(row)
                            existing[key] = row
                            counts["inserted"] += 1
                        else:
                            counts["updated"] += 1
                        for field in ("open", "high", "low", "close", "pre_close", "volume", "amount", "pct_change", "source"):
                            setattr(row, field, getattr(item, field))
                        row.quality_hash = content_hash
                    db.flush()
                totals["instruments"] += 1
                for key in counts:
                    totals[key] += counts[key]
            except Exception as exc:
                error = exc
                totals["failures"].append({"ts_code": instrument.ts_code, "error": type(exc).__name__})
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
        return {"run_id": run_id, "ingestion_policy": "daily-batch-v1", **totals}

    @staticmethod
    def _validated_bar_batch(records, ts_code: str, start_date: date, end_date: date) -> dict:
        """Bound and validate provider records without changing price/indicator formulas."""
        if len(records) > 50_000:
            raise ProviderError("daily history batch exceeds the bounded record limit")
        batch = {}
        for item in records:
            if item.ts_code != ts_code or not isinstance(item.trade_date, date) or isinstance(item.trade_date, datetime):
                raise ProviderError("daily history identity mismatch")
            if not start_date <= item.trade_date <= end_date:
                raise ProviderError("daily history outside requested window")
            if not isinstance(item.adjust, str) or not item.adjust or len(item.adjust) > 8:
                raise ProviderError("daily history adjustment is invalid")
            if not isinstance(item.source, str) or not item.source or len(item.source) > 32:
                raise ProviderError("daily history source is invalid")
            prices = [item.open, item.high, item.low, item.close]
            if any(isinstance(v, bool) or v is None or not math.isfinite(float(v)) or float(v) <= 0 for v in prices):
                raise ProviderError("daily history price is invalid")
            if not item.low <= min(item.open, item.close) <= max(item.open, item.close) <= item.high:
                raise ProviderError("daily history OHLC bounds are inconsistent")
            for name in ("pre_close", "volume", "amount", "pct_change"):
                value = getattr(item, name)
                if value is not None and (isinstance(value, bool) or not math.isfinite(float(value))
                                          or (name != "pct_change" and float(value) < 0)):
                    raise ProviderError("daily history numeric field is invalid")
            key, digest = (item.trade_date, item.adjust), stable_hash(item.to_dict())
            if key in batch and batch[key][1] != digest:
                raise ProviderError("daily history contains conflicting duplicate observations")
            batch[key] = (item, digest)
        return batch

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
        requested_codes = list(by_code)
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
        received_codes = {item.ts_code for item in records if item.ts_code in by_code}
        missing_codes = [code for code in requested_codes if code not in received_codes]
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
                "requested": len(requested_codes),
                "received": len(received_codes),
                "missing": len(missing_codes),
                "missing_codes": missing_codes,
                "run_id": run_id,
            },
        )
        return {
            "run_id": run_id,
            "inserted": inserted,
            "realtime": realtime,
            "raw_realtime": raw_realtime,
            "degraded": degraded,
            "requested": len(requested_codes),
            "received": len(received_codes),
            "missing": len(missing_codes),
            "missing_codes": missing_codes,
        }

    def purge_old_quotes(self, db: Session, keep_days: int = 45) -> int:
        cutoff = datetime.now(self.settings.timezone) - timedelta(days=keep_days)
        result = db.execute(delete(QuoteSnapshot).where(QuoteSnapshot.quote_time < cutoff))
        return int(result.rowcount or 0)

    def refresh_sector_snapshots(self, db: Session, run_id: str | None = None) -> dict:
        """回填行业 / 概念板块涨跌家数与全市场宽度快照（K线企稳看板用）。

        三类数据分别取自 provider 的：
          - fetch_sector_snapshots   → board_type="industry"（行业板块）
          - fetch_concept_snapshots  → board_type="concept"（概念板块）
          - fetch_market_breadth     → board_type="market"（全市场宽度，单条）

        任一类接口不可达（如网络受限）时仅该类别降级为空并告警，不抛出阻断主流程；
        由调用方在消费侧决定对应列显示 "—"。
        """
        run_id = run_id or uuid4().hex
        timer = AuditTimer()

        # (method_name, board_type, is_single) —— is_single: market_breadth 返回单条而非列表
        board_specs = [
            ("fetch_sector_snapshots", "industry", False),
            ("fetch_concept_snapshots", "concept", False),
            ("fetch_market_breadth", "market", True),
        ]

        per_board: dict[str, dict[str, int | str | None]] = {}
        inserted = 0
        errors: list[str] = []
        for method_name, board_type, is_single in board_specs:
            try:
                if not hasattr(self.provider, method_name):
                    raise ProviderError(f"provider 不支持 {method_name}")
                result = getattr(self.provider, method_name)()
                records = [result] if is_single else (result or [])
            except Exception as exc:
                errors.append(f"{board_type}:{type(exc).__name__}")
                logger.warning("sector snapshot refresh [%s] failed (degraded to empty): %s", board_type, exc)
                per_board[board_type] = {"inserted": 0, "error": type(exc).__name__}
                continue

            board_inserted = 0
            for item in records:
                existing = db.scalar(
                    select(SectorSnapshot).where(
                        SectorSnapshot.sector_name == item.sector_name,
                        SectorSnapshot.trade_date == item.trade_date,
                        SectorSnapshot.source == item.source,
                        SectorSnapshot.board_type == item.board_type,
                    )
                )
                if existing:
                    existing.up_count = item.up_count
                    existing.down_count = item.down_count
                    existing.flat_count = item.flat_count
                    existing.total_count = item.total_count
                    existing.pct_change = item.pct_change
                    existing.board_type = item.board_type
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
                            board_type=item.board_type,
                            fetched_at=datetime.now(self.settings.timezone),
                            quality_hash=stable_hash(item.to_dict()),
                        )
                    )
                board_inserted += 1
            inserted += board_inserted
            per_board[board_type] = {"inserted": board_inserted, "error": None}

        db.flush()
        emit_event(
            db,
            "sector_snapshots.updated",
            {"inserted": inserted, "run_id": run_id, "boards": per_board},
        )
        if self.persist_provider_audits:
            record_provider_audit(
                db,
                run_id=run_id,
                operation="refresh_sector_snapshots",
                provider=self.provider,
                result={"inserted": inserted, "boards": per_board},
                error=(errors[0] if errors else None),
                latency_ms=timer.elapsed_ms,
            )
        return {
            "run_id": run_id,
            "inserted": inserted,
            "boards": per_board,
            "error": (errors[0] if errors else None),
        }
