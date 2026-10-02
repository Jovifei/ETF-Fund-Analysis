"""Persist exchange share totals and an adjacent-session 申赎 proxy.

Mock providers are refused before any fetch. Undated snapshots are not stored.
The resulting proxy never grants actionable status.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import EtfShareScale, Instrument, ProviderAudit
from app.providers.base import CapabilityUnavailable, ProviderError
from app.providers.share_scale import ALLOWED_SOURCES, MAX_WINDOW_DAYS
from app.services.audit_service import AuditTimer, record_provider_audit
from app.services.event_service import emit_event
from app.services.trading_calendar_service import TradingCalendarService
from app.utils.hashing import stable_hash

_PROXY_INCREASE = "份额增加"
_PROXY_DECREASE = "份额减少"
_PROXY_FLAT = "份额不变"
_PROXY_UNAVAILABLE = "不可用"


def previous_verified_session(day: date, calendar: TradingCalendarService) -> date | None:
    cursor = day - timedelta(days=1)
    for _ in range(10):
        decision = calendar.decision(cursor)
        if not decision.verified:
            return None
        if decision.is_trade_day:
            return cursor
        cursor -= timedelta(days=1)
    return None


def annotate_share_series(points: list[dict[str, Any]], calendar: TradingCalendarService) -> None:
    points.sort(key=lambda item: item["trade_date"])
    previous: dict[str, Any] | None = None
    for point in points:
        shares = point.get("shares")
        if (
            previous is None
            or previous.get("shares") is None
            or float(previous["shares"]) <= 0
            or shares is None
            or float(shares) < 0
        ):
            point.update(
                previous_trade_date=None,
                previous_shares=None,
                share_delta=None,
                share_delta_ratio=None,
                day_over_day=False,
                proxy=_PROXY_UNAVAILABLE,
            )
        else:
            delta = float(shares) - float(previous["shares"])
            prior = previous_verified_session(point["trade_date"], calendar)
            day_over_day = prior is not None and prior == previous["trade_date"]
            if not day_over_day:
                proxy = _PROXY_UNAVAILABLE
            elif delta > 0:
                proxy = _PROXY_INCREASE
            elif delta < 0:
                proxy = _PROXY_DECREASE
            else:
                proxy = _PROXY_FLAT
            point.update(
                previous_trade_date=previous["trade_date"],
                previous_shares=float(previous["shares"]),
                share_delta=delta,
                share_delta_ratio=delta / float(previous["shares"]),
                day_over_day=day_over_day,
                proxy=proxy,
            )
        previous = point


class ShareScaleService:
    def __init__(
        self,
        provider: Any,
        settings: Settings | None = None,
        *,
        calendar: TradingCalendarService | None = None,
    ) -> None:
        self.provider = provider
        self.settings = settings or get_settings()
        self.calendar = calendar or TradingCalendarService(self.settings, provider)

    def refresh(
        self,
        db: Session,
        *,
        codes: list[str] | None = None,
        lookback_days: int | None = None,
        as_of: date | None = None,
        run_id: str,
    ) -> dict[str, Any]:
        instruments = self._instruments(db, codes)
        requested = [item.ts_code for item in instruments]
        if getattr(self.provider, "name", "") == "mock":
            self._audit_skip(db, run_id, "mock_share_scale_blocked")
            result = self._done(
                run_id,
                status="skipped",
                reason="mock_share_scale_blocked",
                requested=len(requested),
                completed=0,
                inserted=0,
                updated=0,
                unchanged=0,
            )
            emit_event(db, "share_scales.updated", dict(result))
            return result
        if not instruments:
            result = self._done(
                run_id,
                status="skipped",
                reason="no_instruments",
                requested=0,
                completed=0,
                inserted=0,
                updated=0,
                unchanged=0,
            )
            emit_event(db, "share_scales.updated", dict(result))
            return result

        end = as_of or datetime.now(self.settings.timezone).date()
        span = min(max(int(lookback_days or 8), 2), MAX_WINDOW_DAYS)
        start = end - timedelta(days=span - 1)
        timer = AuditTimer()
        error: Exception | None = None
        records: list[Any] = []
        try:
            records = list(self.provider.fetch_share_scales(requested, start, end) or [])
            records = [row for row in records if str(getattr(row, "source", "")) in ALLOWED_SOURCES and "mock" not in str(row.source).lower()]
        except CapabilityUnavailable as exc:
            error = exc
            record_provider_audit(
                db, run_id=run_id, operation="fetch_share_scales", provider=self.provider,
                result=[], error=exc, latency_ms=timer.elapsed_ms,
            )
            result = self._done(
                run_id, status="failed", reason="share_scale_endpoint_unavailable",
                requested=len(requested), completed=0, inserted=0, updated=0, unchanged=0,
                window_days=span, window_capped=bool(lookback_days and lookback_days > MAX_WINDOW_DAYS),
            )
            emit_event(db, "share_scales.updated", dict(result))
            return result
        except Exception as exc:
            error = exc if isinstance(exc, ProviderError) else ProviderError("share_scale_fetch_failed")
            record_provider_audit(
                db, run_id=run_id, operation="fetch_share_scales", provider=self.provider,
                result=[], error=error, latency_ms=timer.elapsed_ms,
            )
            result = self._done(
                run_id, status="failed", reason=str(error),
                requested=len(requested), completed=0, inserted=0, updated=0, unchanged=0,
                window_days=span, window_capped=bool(lookback_days and lookback_days > MAX_WINDOW_DAYS),
            )
            emit_event(db, "share_scales.updated", dict(result))
            return result
        record_provider_audit(
            db, run_id=run_id, operation="fetch_share_scales", provider=self.provider,
            result=records, error=None, latency_ms=timer.elapsed_ms,
        )
        by_code = {item.ts_code: item for item in instruments}
        grouped: dict[tuple[int, str], list[dict[str, Any]]] = {}
        seen: set[str] = set()
        for row in records:
            instrument = by_code.get(str(row.ts_code).upper())
            if instrument is None:
                continue
            seen.add(instrument.ts_code)
            grouped.setdefault((instrument.id, row.source), []).append(
                {
                    "instrument_id": instrument.id,
                    "trade_date": row.trade_date,
                    "shares": float(row.shares),
                    "source": row.source,
                    "exchange": row.exchange,
                }
            )
        existing = db.scalars(
            select(EtfShareScale).where(EtfShareScale.instrument_id.in_([item.id for item in instruments]))
        ).all() if instruments else []
        stored = {(row.instrument_id, row.source, row.trade_date): row for row in existing}
        for key, points in list(grouped.items()):
            known = [
                {
                    "instrument_id": row.instrument_id,
                    "trade_date": row.trade_date,
                    "shares": row.shares,
                    "source": row.source,
                    "exchange": row.exchange,
                }
                for (instrument_id, source, _trade_date), row in stored.items()
                if (instrument_id, source) == key
            ]
            merged = {(item["trade_date"]): item for item in known}
            for item in points:
                merged[item["trade_date"]] = item
            series = list(merged.values())
            annotate_share_series(series, self.calendar)
            grouped[key] = series

        inserted = updated = unchanged = 0
        fetched_at = datetime.now(self.settings.timezone)
        for series in grouped.values():
            for point in series:
                payload = {
                    "shares": point["shares"],
                    "previous_trade_date": point["previous_trade_date"],
                    "previous_shares": point["previous_shares"],
                    "share_delta": point["share_delta"],
                    "share_delta_ratio": point["share_delta_ratio"],
                    "day_over_day": point["day_over_day"],
                    "proxy": point["proxy"],
                    "exchange": point["exchange"],
                }
                quality = stable_hash(payload)
                current = stored.get((point["instrument_id"], point["source"], point["trade_date"]))
                if current is None:
                    db.add(
                        EtfShareScale(
                            instrument_id=point["instrument_id"],
                            trade_date=point["trade_date"],
                            shares=point["shares"],
                            previous_trade_date=point["previous_trade_date"],
                            previous_shares=point["previous_shares"],
                            share_delta=point["share_delta"],
                            share_delta_ratio=point["share_delta_ratio"],
                            day_over_day=bool(point["day_over_day"]),
                            proxy=point["proxy"],
                            source=point["source"],
                            exchange=point["exchange"],
                            fetched_at=fetched_at,
                            quality_hash=quality,
                        )
                    )
                    inserted += 1
                    continue
                if current.quality_hash == quality and current.proxy == point["proxy"]:
                    unchanged += 1
                    continue
                current.shares = point["shares"]
                current.previous_trade_date = point["previous_trade_date"]
                current.previous_shares = point["previous_shares"]
                current.share_delta = point["share_delta"]
                current.share_delta_ratio = point["share_delta_ratio"]
                current.day_over_day = bool(point["day_over_day"])
                current.proxy = point["proxy"]
                current.exchange = point["exchange"]
                current.fetched_at = fetched_at
                current.quality_hash = quality
                updated += 1
        db.flush()
        missing = [code for code in requested if code not in seen]
        result = self._done(
            run_id,
            status="succeeded",
            reason=None,
            requested=len(requested),
            completed=len(seen),
            inserted=inserted,
            updated=updated,
            unchanged=unchanged,
            missing_codes=missing,
            window_days=span,
            window_capped=bool(lookback_days and int(lookback_days) > MAX_WINDOW_DAYS),
        )
        if missing or error is not None:
            result["status"] = "partial" if seen else "failed"
        emit_event(db, "share_scales.updated", dict(result))
        return result

    def _instruments(self, db: Session, codes: list[str] | None) -> list[Instrument]:
        rows = db.scalars(select(Instrument).where(Instrument.enabled.is_(True)).order_by(Instrument.ts_code)).all()
        if not codes:
            return list(rows)
        wanted = {str(code).strip().upper() for code in codes}
        return [row for row in rows if row.ts_code.upper() in wanted or row.symbol.upper() in wanted]

    def _audit_skip(self, db: Session, run_id: str, reason: str) -> None:
        db.add(
            ProviderAudit(
                run_id=run_id,
                operation="fetch_share_scales",
                provider=str(getattr(self.provider, "name", "unknown"))[:32],
                status="skipped",
                latency_ms=0,
                record_count=0,
                reason=reason,
            )
        )

    @staticmethod
    def _done(
        run_id: str,
        *,
        status: str,
        reason: str | None,
        requested: int,
        completed: int,
        inserted: int,
        updated: int,
        unchanged: int,
        missing_codes: list[str] | None = None,
        window_days: int | None = None,
        window_capped: bool = False,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "run_id": run_id,
            "status": status,
            "requested": requested,
            "completed": completed,
            "inserted": inserted,
            "updated": updated,
            "unchanged": unchanged,
            "missing_codes": list(missing_codes or []),
            "window_days": window_days,
            "window_capped": window_capped,
            "research_only": True,
            "actionable": False,
        }
        if reason:
            result["reason"] = reason
        return result
