"""Research-only HS300 passive-holdings ratio.

Zero-credential and forward-only: the denominator is a same-day Eastmoney
market-cap snapshot with no upstream trade date, so this service refuses any
date it did not observe after the close. It never back-fills, never guesses a
missing fund, and never turns the ratio into a grade, ``actionable`` flag or
position instruction.

Numerator bases (both requested by the owner on 2026-10-29):

* ``market_value_at_close`` — 份额 × 当日收盘价 (二级市场市值代理)
* ``aum_at_nav`` — 份额 × 单位净值 (接近资产净值)

Each basis is stored separately; a failure of one does not invent the other.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import DailyBar, EtfShareScale, Hs300PassiveRatioSnapshot, Instrument, ProviderAudit
from app.providers.base import CapabilityUnavailable, ProviderError
from app.providers.share_scale import ALLOWED_SOURCES as ALLOWED_SHARE_SOURCES
from app.services.audit_service import AuditTimer, record_provider_audit
from app.services.event_service import emit_event
from app.services.hs300_ratio import (
    AUM_AT_NAV,
    FLOAT_MARKET_CAP,
    MARKET_VALUE_AT_CLOSE,
    UNIVERSE_CONFIRMED,
    compute_ratio,
    load_universe,
    normalize_funds,
    universe_hash,
)
from app.services.settlement import SETTLEMENT_CUTOFF
from app.utils.hashing import stable_hash

CLOSE_NUMERATOR_SOURCE = "etf_share_scales+daily_bars:close"
NAV_NUMERATOR_SOURCE = "etf_share_scales+fund_etf_fund_daily_em"
AUDIT_OPERATION = "fetch_hs300_ratio"


class Hs300RatioService:
    def __init__(self, provider: Any, settings: Settings | None = None) -> None:
        self.provider = provider
        self.settings = settings or get_settings()

    def refresh(self, db: Session, *, as_of: date | None = None, run_id: str) -> dict[str, Any]:
        from app.services.research_write_guard import require_research_write

        require_research_write(self.settings, "Hs300RatioService.refresh")
        as_of = as_of or datetime.now(self.settings.timezone).date()

        if getattr(self.provider, "name", "") == "mock":
            return self._precondition(db, run_id, as_of, "mock_ratio_blocked")

        universe = load_universe(self.settings.hs300_universe_path)
        index_code = str(universe.get("index_code") or "000300.SH").strip().upper()
        if universe.get("reason"):
            return self._precondition(db, run_id, as_of, str(universe["reason"]), index_code=index_code)
        if str(universe.get("status") or "").strip().lower() != UNIVERSE_CONFIRMED:
            return self._precondition(db, run_id, as_of, "universe_not_confirmed", index_code=index_code)

        funds, rejected = normalize_funds(universe.get("funds"))
        if rejected or not funds:
            return self._precondition(db, run_id, as_of, "universe_invalid", index_code=index_code)
        expected_hash = universe_hash(index_code, funds)
        if universe.get("universe_hash") != expected_hash:
            return self._precondition(
                db, run_id, as_of, "universe_hash_mismatch",
                index_code=index_code, universe_hash=expected_hash,
            )

        constituents, failure = self._fetch_constituents(db, run_id, index_code)
        if failure is not None:
            return self._fail(db, run_id, as_of, failure, index_code=index_code, universe_hash=expected_hash)

        snapshot, failure = self._fetch_market_caps(db, run_id)
        if failure is not None:
            return self._fail(db, run_id, as_of, failure, index_code=index_code, universe_hash=expected_hash)

        observed = getattr(snapshot, "observed_at", None)
        if not isinstance(observed, datetime):
            return self._fail(db, run_id, as_of, "snapshot_undated",
                              index_code=index_code, universe_hash=expected_hash)
        local = observed.astimezone(self.settings.timezone) if observed.tzinfo else observed.replace(
            tzinfo=self.settings.timezone
        )
        if local.date() != as_of:
            return self._fail(
                db, run_id, as_of, "snapshot_not_as_of",
                index_code=index_code, universe_hash=expected_hash,
                observed_on=local.date().isoformat(),
            )
        if local.time().replace(tzinfo=None) < SETTLEMENT_CUTOFF:
            return self._fail(db, run_id, as_of, "snapshot_before_close",
                              index_code=index_code, universe_hash=expected_hash)

        float_by_code = {
            row.ts_code: float(row.float_mv)
            for row in snapshot.rows
            if getattr(row, "float_mv", None) is not None and float(row.float_mv) > 0
        }
        constituent_codes = [row.ts_code for row in constituents]
        missing = [code for code in constituent_codes if code not in float_by_code]
        if missing:
            return self._fail(
                db, run_id, as_of, "constituent_coverage_incomplete",
                index_code=index_code, universe_hash=expected_hash,
                missing_constituents=len(missing), constituent_count=len(constituent_codes),
            )
        denominator = sum(float_by_code[code] for code in constituent_codes)
        if denominator <= 0:
            return self._fail(db, run_id, as_of, "denominator_non_positive",
                              index_code=index_code, universe_hash=expected_hash)

        instruments = {
            row.ts_code: row
            for row in db.scalars(select(Instrument).where(Instrument.ts_code.in_(funds))).all()
        }
        missing_instruments = [code for code in funds if code not in instruments]
        if missing_instruments:
            return self._fail(
                db, run_id, as_of, "fund_instrument_missing",
                index_code=index_code, universe_hash=expected_hash,
                missing_funds=len(missing_instruments),
            )
        instrument_ids = [instruments[code].id for code in funds]

        shares = self._latest_shares(db, instrument_ids, as_of)
        missing_shares = [code for code in funds if instruments[code].id not in shares]
        if missing_shares:
            return self._fail(
                db, run_id, as_of, "fund_shares_missing",
                index_code=index_code, universe_hash=expected_hash,
                missing_funds=len(missing_shares),
            )
        closes = self._latest_closes(db, instrument_ids, as_of)
        missing_closes = [code for code in funds if instruments[code].id not in closes]
        share_by_code = {code: shares[instruments[code].id] for code in funds}
        close_by_code = {code: closes[instruments[code].id] for code in funds if code not in missing_closes}

        navs, nav_reason = self._fetch_navs(db, run_id, funds)
        for code in funds:
            if code not in navs and nav_reason is None:
                nav_reason = "fund_nav_missing"

        computed_at = datetime.now(self.settings.timezone)
        constituent_as_of = max((row.as_of for row in constituents), default=None)
        bases: dict[str, dict[str, Any]] = {}
        unavailable: dict[str, str] = {}

        if missing_closes:
            unavailable[MARKET_VALUE_AT_CLOSE] = "fund_close_missing"
        else:
            numerator = sum(share_by_code[code] * close_by_code[code] for code in funds)
            ratio = compute_ratio(numerator, denominator)
            if ratio is None:
                unavailable[MARKET_VALUE_AT_CLOSE] = "ratio_out_of_bounds"
            else:
                bases[MARKET_VALUE_AT_CLOSE] = {
                    "basis": FLOAT_MARKET_CAP,
                    "numerator": numerator,
                    "denominator": denominator,
                    "ratio": ratio,
                    "fund_count": len(funds),
                    "constituent_count": len(constituent_codes),
                    "constituent_as_of": constituent_as_of.isoformat() if constituent_as_of else None,
                    "numerator_source": CLOSE_NUMERATOR_SOURCE,
                    "denominator_source": snapshot.source,
                    "lag_days": 0,
                }

        if nav_reason is not None:
            unavailable[AUM_AT_NAV] = nav_reason
        else:
            numerator = sum(share_by_code[code] * float(navs[code].nav) for code in funds)
            ratio = compute_ratio(numerator, denominator)
            if ratio is None:
                unavailable[AUM_AT_NAV] = "ratio_out_of_bounds"
            else:
                lag = max((as_of - navs[code].nav_date).days for code in funds)
                bases[AUM_AT_NAV] = {
                    "basis": FLOAT_MARKET_CAP,
                    "numerator": numerator,
                    "denominator": denominator,
                    "ratio": ratio,
                    "fund_count": len(funds),
                    "constituent_count": len(constituent_codes),
                    "constituent_as_of": constituent_as_of.isoformat() if constituent_as_of else None,
                    "numerator_source": NAV_NUMERATOR_SOURCE,
                    "denominator_source": snapshot.source,
                    "lag_days": max(0, lag),
                }

        inserted = updated = unchanged = 0
        for numerator_basis, payload in bases.items():
            quality = stable_hash(
                {
                    "index_code": index_code,
                    "trade_date": as_of.isoformat(),
                    "basis": payload["basis"],
                    "numerator_basis": numerator_basis,
                    "numerator": payload["numerator"],
                    "denominator": payload["denominator"],
                    "ratio": payload["ratio"],
                    "fund_count": payload["fund_count"],
                    "constituent_count": payload["constituent_count"],
                    "universe_hash": expected_hash,
                    "numerator_source": payload["numerator_source"],
                    "denominator_source": payload["denominator_source"],
                    "lag_days": payload["lag_days"],
                }
            )
            current = db.scalar(
                select(Hs300PassiveRatioSnapshot).where(
                    Hs300PassiveRatioSnapshot.trade_date == as_of,
                    Hs300PassiveRatioSnapshot.numerator_basis == numerator_basis,
                )
            )
            if current is None:
                db.add(
                    Hs300PassiveRatioSnapshot(
                        trade_date=as_of,
                        index_code=index_code,
                        basis=payload["basis"],
                        numerator_basis=numerator_basis,
                        numerator=payload["numerator"],
                        denominator=payload["denominator"],
                        ratio=payload["ratio"],
                        fund_count=payload["fund_count"],
                        universe_hash=expected_hash,
                        constituent_count=payload["constituent_count"],
                        constituent_as_of=constituent_as_of,
                        numerator_source=payload["numerator_source"],
                        denominator_source=payload["denominator_source"],
                        lag_days=payload["lag_days"],
                        computed_at=computed_at,
                        quality_hash=quality,
                    )
                )
                inserted += 1
                continue
            if current.quality_hash == quality:
                unchanged += 1
                continue
            current.index_code = index_code
            current.basis = payload["basis"]
            current.numerator = payload["numerator"]
            current.denominator = payload["denominator"]
            current.ratio = payload["ratio"]
            current.fund_count = payload["fund_count"]
            current.universe_hash = expected_hash
            current.constituent_count = payload["constituent_count"]
            current.constituent_as_of = constituent_as_of
            current.numerator_source = payload["numerator_source"]
            current.denominator_source = payload["denominator_source"]
            current.lag_days = payload["lag_days"]
            current.computed_at = computed_at
            current.quality_hash = quality
            updated += 1
        db.flush()

        if not bases:
            reason = next(iter(unavailable.values()), "ratio_unavailable")
            payload = self._result(
                run_id, as_of, status="failed", reason=reason, index_code=index_code,
                universe_hash=expected_hash, fund_count=len(funds),
                constituent_count=len(constituent_codes), bases=bases, unavailable_reasons=unavailable,
                inserted=inserted, updated=updated, unchanged=unchanged,
            )
        else:
            payload = self._result(
                run_id, as_of,
                status="partial" if unavailable else "succeeded",
                reason=None, index_code=index_code,
                universe_hash=expected_hash, fund_count=len(funds),
                constituent_count=len(constituent_codes), bases=bases, unavailable_reasons=unavailable,
                inserted=inserted, updated=updated, unchanged=unchanged,
            )
        emit_event(db, "hs300_ratio.updated", dict(payload))
        return payload

    # ---- provider reads -------------------------------------------------

    def _fetch_constituents(self, db: Session, run_id: str, index_code: str):
        timer = AuditTimer()
        try:
            rows = list(self.provider.fetch_index_constituents(index_code) or [])
        except CapabilityUnavailable as exc:
            record_provider_audit(
                db, run_id=run_id, operation="fetch_index_constituents", provider=self.provider,
                result=[], error=exc, latency_ms=timer.elapsed_ms,
            )
            return [], "constituent_endpoint_unavailable"
        except Exception:
            error = ProviderError("index_constituent_fetch_failed")
            record_provider_audit(
                db, run_id=run_id, operation="fetch_index_constituents", provider=self.provider,
                result=[], error=error, latency_ms=timer.elapsed_ms,
            )
            return [], "constituent_fetch_failed"
        record_provider_audit(
            db, run_id=run_id, operation="fetch_index_constituents", provider=self.provider,
            result=rows, error=None, latency_ms=timer.elapsed_ms,
        )
        if not rows:
            return [], "constituent_endpoint_unavailable"
        return rows, None

    def _fetch_market_caps(self, db: Session, run_id: str):
        timer = AuditTimer()
        try:
            snapshot = self.provider.fetch_stock_float_market_caps()
        except CapabilityUnavailable as exc:
            record_provider_audit(
                db, run_id=run_id, operation="fetch_stock_float_market_caps", provider=self.provider,
                result=[], error=exc, latency_ms=timer.elapsed_ms,
            )
            return None, "denominator_endpoint_unavailable"
        except Exception:
            error = ProviderError("stock_market_cap_fetch_failed")
            record_provider_audit(
                db, run_id=run_id, operation="fetch_stock_float_market_caps", provider=self.provider,
                result=[], error=error, latency_ms=timer.elapsed_ms,
            )
            return None, "denominator_fetch_failed"
        record_provider_audit(
            db, run_id=run_id, operation="fetch_stock_float_market_caps", provider=self.provider,
            result=getattr(snapshot, "rows", []), error=None, latency_ms=timer.elapsed_ms,
        )
        return snapshot, None

    def _fetch_navs(self, db: Session, run_id: str, funds: list[str]):
        timer = AuditTimer()
        try:
            rows = list(self.provider.fetch_etf_nav_snapshot() or [])
        except CapabilityUnavailable as exc:
            record_provider_audit(
                db, run_id=run_id, operation="fetch_etf_nav_snapshot", provider=self.provider,
                result=[], error=exc, latency_ms=timer.elapsed_ms,
            )
            return {}, "nav_endpoint_unavailable"
        except Exception:
            error = ProviderError("fund_nav_fetch_failed")
            record_provider_audit(
                db, run_id=run_id, operation="fetch_etf_nav_snapshot", provider=self.provider,
                result=[], error=error, latency_ms=timer.elapsed_ms,
            )
            return {}, "nav_fetch_failed"
        record_provider_audit(
            db, run_id=run_id, operation="fetch_etf_nav_snapshot", provider=self.provider,
            result=rows, error=None, latency_ms=timer.elapsed_ms,
        )
        wanted = set(funds)
        selected = {
            row.ts_code: row
            for row in rows
            if row.ts_code in wanted and row.nav is not None and float(row.nav) > 0
        }
        return selected, None

    # ---- stored inputs --------------------------------------------------

    @staticmethod
    def _latest_shares(db: Session, instrument_ids: list[int], as_of: date) -> dict[int, float]:
        if not instrument_ids:
            return {}
        rows = db.scalars(
            select(EtfShareScale)
            .where(
                EtfShareScale.instrument_id.in_(instrument_ids),
                EtfShareScale.trade_date == as_of,
            )
            .order_by(EtfShareScale.id)
        ).all()
        latest: dict[int, float] = {}
        for row in rows:
            if row.source not in ALLOWED_SHARE_SOURCES or "mock" in str(row.source).lower():
                continue
            if row.shares is None or float(row.shares) <= 0:
                continue
            latest[row.instrument_id] = float(row.shares)
        return latest

    @staticmethod
    def _latest_closes(db: Session, instrument_ids: list[int], as_of: date) -> dict[int, float]:
        if not instrument_ids:
            return {}
        rows = db.scalars(
            select(DailyBar)
            .where(
                DailyBar.instrument_id.in_(instrument_ids),
                DailyBar.trade_date == as_of,
                DailyBar.adjust == "none",
            )
            .order_by(DailyBar.id)
        ).all()
        latest: dict[int, float] = {}
        for row in rows:
            if row.close is None or float(row.close) <= 0:
                continue
            latest[row.instrument_id] = float(row.close)
        return latest

    # ---- result plumbing ------------------------------------------------

    def _precondition(self, db: Session, run_id: str, as_of: date, reason: str, **extra) -> dict[str, Any]:
        self._audit_skip(db, run_id, reason)
        payload = self._result(run_id, as_of, status="skipped", reason=reason, **extra)
        emit_event(db, "hs300_ratio.updated", dict(payload))
        return payload

    def _fail(self, db: Session, run_id: str, as_of: date, reason: str, **extra) -> dict[str, Any]:
        payload = self._result(run_id, as_of, status="failed", reason=reason, **extra)
        emit_event(db, "hs300_ratio.updated", dict(payload))
        return payload

    def _audit_skip(self, db: Session, run_id: str, reason: str) -> None:
        db.add(
            ProviderAudit(
                run_id=run_id,
                operation=AUDIT_OPERATION,
                provider=str(getattr(self.provider, "name", "unknown"))[:32],
                status="skipped",
                latency_ms=0,
                record_count=0,
                reason=reason,
            )
        )

    @staticmethod
    def _result(
        run_id: str,
        as_of: date,
        *,
        status: str,
        reason: str | None,
        **extra: Any,
    ) -> dict[str, Any]:
        bases = extra.pop("bases", None) or {}
        unavailable = extra.pop("unavailable_reasons", None) or {}
        payload: dict[str, Any] = {
            "run_id": run_id,
            "status": status,
            "as_of": as_of.isoformat(),
            "basis": FLOAT_MARKET_CAP,
            "ratio_status": "computed" if bases else "unavailable",
            "bases": bases,
            "unavailable_reasons": unavailable,
            "inserted": 0,
            "updated": 0,
            "unchanged": 0,
            "research_only": True,
            "actionable": False,
            "changes_grade": False,
            "qualification": "UNKNOWN",
            "calibration_status": "not_calibrated",
        }
        if reason:
            payload["reason"] = reason
        # Caller counters (inserted/updated/unchanged and gate metadata) win
        # over the zero defaults above.
        payload.update(extra)
        return payload
