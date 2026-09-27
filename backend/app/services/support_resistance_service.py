"""支撑/压力唯一计算与读取入口（support-resistance-v4-structure）。

全系统的支撑压力只在这里计算并落库（SupportResistanceSnapshot），
决策总表 / 14:30 工作台 / ETF 详情一律读取快照，禁止各自从日线重算。

统一输入口径（修复方案 P0-5）：
* 回溯窗口 250 根已存日线；按统一公司行为研究口径计算，原始行情不改写；
* 保留真实 ``amount/volume`` 的空值与零值，不估算或填零；
* 参数来自 ``config/etf_1430_workbench.json`` 的 ``support_resistance`` 块。
"""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT, Settings, get_settings
from app.models import DailyBar, Instrument, SupportResistanceSnapshot, SupportResistanceSnapshotRevision
from app.utils.hashing import stable_hash
from app.utils.price_structure import ALGORITHM_VERSION, build_price_structures
from app.utils.support_resistance import build_support_resistance

logger = logging.getLogger(__name__)

METHOD_VERSION = "support-resistance-v4-structure"
DEFAULT_WINDOW = 250
SHANGHAI = ZoneInfo("Asia/Shanghai")
DAILY_SETTLEMENT = time(15, 15)

_EMPTY_PAYLOAD: dict[str, Any] = {
    "qualified": False,
    "reason": "history_too_short",
    "levels": [],
    "nearest_support": None,
    "nearest_resistance": None,
    "trend_lines": [],
    "chan_zone_approx": None,
    "structures": {"qualified": False, "reason": "snapshot_missing_requires_task", "boxes": [], "actionable": False},
}


def _snapshot_revision_id(
    *,
    instrument_id: int,
    as_of_date,
    method_version: str,
    config_hash: str | None,
    price_basis_id: str | None,
    input_hash: str | None,
    payload_hash: str,
) -> str:
    return stable_hash({
        "instrument_id": instrument_id,
        "interval": "1d",
        "as_of_date": as_of_date,
        "method_version": method_version,
        "config_hash": config_hash,
        "price_basis_id": price_basis_id,
        "input_hash": input_hash,
        "payload_hash": payload_hash,
    })


def _revision_is_self_consistent(
    revision: SupportResistanceSnapshotRevision,
    *,
    expected_revision_id: str,
) -> bool:
    """Validate immutable evidence content and its content-addressed identity."""
    if stable_hash(revision.payload_json) != revision.payload_hash:
        return False
    derived_revision_id = _snapshot_revision_id(
        instrument_id=revision.instrument_id,
        as_of_date=revision.as_of_date,
        method_version=revision.method_version,
        config_hash=revision.config_hash,
        price_basis_id=revision.price_basis_id,
        input_hash=revision.input_hash,
        payload_hash=revision.payload_hash,
    )
    return derived_revision_id == revision.revision_id == expected_revision_id


class SupportResistanceService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.config = self._load_config()
        self.config_hash = stable_hash(self.config)

    def _load_config(self) -> dict[str, Any]:
        path = PROJECT_ROOT / "config" / "etf_1430_workbench.json"
        if not path.is_file():
            return {}
        try:
            import json

            block = json.loads(path.read_text(encoding="utf-8")).get("support_resistance", {})
            return dict(block) if isinstance(block, dict) else {}
        except (OSError, ValueError) as exc:
            logger.warning("support_resistance config unreadable: %s", exc)
            return {}

    # -------------------------------------------------------------- 数据准备

    def _sr_frame(self, db: Session, instrument_id: int, *, window: int = DEFAULT_WINDOW,
                  as_of: datetime | None = None) -> pd.DataFrame:
        """Bounded research history; unknown units may not feed weighted methods."""
        from app.providers.corporate_action_contract import research_history_rows, research_price_basis
        from app.providers.data_contract import finite, price_history_issue, row_units_verified
        from app.utils.input_lineage import history_digest
        assessed_at = as_of or datetime.now(SHANGHAI)
        if assessed_at.tzinfo is None:
            assessed_at = assessed_at.replace(tzinfo=SHANGHAI)
        assessed_at = assessed_at.astimezone(SHANGHAI)
        last_settled_date = assessed_at.date() if assessed_at.time() >= DAILY_SETTLEMENT else assessed_at.date() - timedelta(days=1)
        rows = list(reversed(db.scalars(select(DailyBar)
            .where(DailyBar.instrument_id == instrument_id, DailyBar.trade_date <= last_settled_date)
            .order_by(DailyBar.trade_date.desc(), DailyBar.id.desc()).limit(window)).all()))
        instrument = db.get(Instrument, instrument_id)
        research_rows = rows if self.settings.market_provider == "mock" or instrument is None else research_history_rows(rows, instrument.ts_code)
        adjustments = {row.adjust for row in rows}
        adjust = next(iter(adjustments)) if len(adjustments) == 1 else None
        price_changed = any(
            finite(getattr(source_row, key, None)) and finite(getattr(row, key, None))
            and abs(float(getattr(source_row, key)) - float(getattr(row, key))) > 1e-12
            for source_row, row in zip(rows, research_rows, strict=True)
            for key in ("open", "high", "low", "close")
        )
        basis_descriptor = research_price_basis(
            instrument.ts_code if instrument else str(instrument_id),
            adjust,
            effective_through=last_settled_date,
            consider_corporate_actions=self.settings.market_provider != "mock",
        )
        basis = str(basis_descriptor["basis"])
        basis_id = str(basis_descriptor["price_basis_id"])
        records = []
        for source_row, row in zip(rows, research_rows, strict=True):
            units_ok = row_units_verified(source_row) or (self.settings.market_provider == "mock" and "mock" in source_row.source)
            records.append({"trade_date": row.trade_date, "open": row.open, "high": row.high,
                "low": row.low, "close": row.close,
                "volume": row.volume if units_ok and finite(row.volume) and row.volume >= 0 else None,
                "amount": row.amount if units_ok and finite(row.amount) and row.amount >= 0 else None})
        frame = pd.DataFrame(records)
        frame.attrs["history_issue"] = price_history_issue(research_rows)
        frame.attrs["input_hash"] = stable_hash({"raw_history_hash": history_digest(rows), "price_basis_id": basis_id})
        prefix_hashes: dict[str, str] = {}
        previous_hash = "0" * 64
        for source_row, research_row in zip(rows, research_rows, strict=True):
            source_input = {key: getattr(source_row, key, None) for key in (
                "trade_date", "open", "high", "low", "close", "pre_close", "volume", "amount", "pct_change", "adjust", "source")}
            research_input = {key: getattr(research_row, key, None) for key in ("trade_date", "open", "high", "low", "close", "volume", "amount")}
            previous_hash = stable_hash({"prior": previous_hash, "source": source_input,
                "research": research_input, "price_basis_id": basis_id})
            prefix_hashes[research_row.trade_date.isoformat()] = previous_hash
        frame.attrs["prefix_input_hashes"] = prefix_hashes
        frame.attrs["price_basis_id"] = basis_id
        frame.attrs["price_basis"] = basis
        frame.attrs["instrument"] = instrument.ts_code if instrument else str(instrument_id)
        frame.attrs["contains_mock"] = any("mock" in str(row.source).lower() for row in rows)
        return frame

    # -------------------------------------------------------------- 计算/落库

    def _upsert(
        self,
        db: Session,
        instrument_id: int,
        payload: dict[str, Any],
        *,
        as_of_date,
        bars: int,
        computed_by: str,
    ) -> None:
        if as_of_date is None:
            return
        payload_hash = stable_hash(payload)
        input_hash = payload.get("input_hash")
        price_basis_id = payload.get("price_basis_id")
        revision_id = _snapshot_revision_id(
            instrument_id=instrument_id,
            as_of_date=as_of_date,
            method_version=METHOD_VERSION,
            config_hash=self.config_hash,
            price_basis_id=price_basis_id,
            input_hash=input_hash,
            payload_hash=payload_hash,
        )
        if db.scalar(select(SupportResistanceSnapshotRevision).where(
            SupportResistanceSnapshotRevision.revision_id == revision_id
        )) is None:
            db.add(SupportResistanceSnapshotRevision(
                revision_id=revision_id,
                instrument_id=instrument_id,
                interval="1d",
                as_of_date=as_of_date,
                method_version=METHOD_VERSION,
                config_hash=self.config_hash,
                price_basis_id=price_basis_id,
                input_hash=input_hash,
                payload_hash=payload_hash,
                payload_json=payload,
                source_bars=bars,
                computed_by=computed_by,
            ))
        existing = db.scalar(
            select(SupportResistanceSnapshot).where(
                SupportResistanceSnapshot.instrument_id == instrument_id,
                SupportResistanceSnapshot.interval == "1d",
                SupportResistanceSnapshot.as_of_date == as_of_date,
            )
        )
        if existing is not None:
            existing.payload_json = payload
            existing.current_price = payload.get("current_price")
            existing.qualified = bool(payload.get("qualified"))
            existing.config_hash = self.config_hash
            existing.source_bars = bars
            existing.computed_by = computed_by
            existing.method_version = METHOD_VERSION
            existing.generated_at = datetime.now(timezone.utc)
        else:
            db.add(
                SupportResistanceSnapshot(
                    instrument_id=instrument_id,
                    interval="1d",
                    as_of_date=as_of_date,
                    current_price=payload.get("current_price"),
                    qualified=bool(payload.get("qualified")),
                    payload_json=payload,
                    method_version=METHOD_VERSION,
                    config_hash=self.config_hash,
                    source_bars=bars,
                    computed_by=computed_by,
                )
            )
        db.flush()

    def compute(self, db: Session, instrument_id: int, *, computed_by: str = "scheduled",
                as_of: datetime | None = None) -> dict[str, Any]:
        """显式任务计算并落库；页面读取不触发本方法。"""
        frame = self._sr_frame(db, instrument_id, as_of=as_of)
        bars = len(frame)
        issue = frame.attrs.get("history_issue")
        payload = ({**_EMPTY_PAYLOAD, "reason": issue} if issue
                   else build_support_resistance(frame, self.config))
        structures = {"qualified": False, "reason": issue, "boxes": [], "actionable": False,
                      "algorithm_version": ALGORITHM_VERSION, "price_basis_id": frame.attrs.get("price_basis_id"),
                      "input_hash": frame.attrs.get("input_hash"), "interval": "1d"}
        if not issue and bars:
            expected_dates = None
            calendar_issue = None
            if not frame.attrs.get("contains_mock"):
                try:
                    import exchange_calendars as xcals

                    calendar = xcals.get_calendar("XSHG")
                    sessions = calendar.sessions_in_range(frame.iloc[0]["trade_date"].isoformat(), frame.iloc[-1]["trade_date"].isoformat())
                    expected_dates = [pd.Timestamp(day).date().isoformat() for day in sessions]
                except Exception as exc:  # noqa: BLE001 - no verified calendar means no box certification
                    calendar_issue = f"calendar_unavailable:{type(exc).__name__}"
            if calendar_issue:
                structures["reason"] = "calendar_unavailable"
                structures["calendar_detail"] = calendar_issue
            else:
                structures = build_price_structures(frame, instrument=str(frame.attrs.get("instrument") or instrument_id),
                    price_basis_id=str(frame.attrs.get("price_basis_id") or "unknown"),
                    config=self.config.get("price_structure", {}), expected_dates=expected_dates,
                    input_hash=str(frame.attrs.get("input_hash") or ""),
                    input_hashes_by_date=frame.attrs.get("prefix_input_hashes"))
        structures["source_as_of_date"] = frame.iloc[-1]["trade_date"].isoformat() if bars else None
        payload["structures"] = structures
        payload["price_basis_id"] = frame.attrs.get("price_basis_id")
        volume_ready = bool(bars and frame["volume"].notna().all())
        amount_ready = bool(bars and frame["amount"].notna().all())
        payload.update(method_version=METHOD_VERSION, config_hash=self.config_hash,
            input_hash=frame.attrs.get("input_hash"), actionable=False,
            qualification="mock" if frame.attrs.get("contains_mock") else "blocked" if issue
                          else "price_only_research" if not volume_ready else "research_only",
            input_availability={"volume": volume_ready, "amount": amount_ready, "estimated_amount": False},
            qualified_semantics="price_structure_computable_not_trading_approval")
        as_of_date = frame.iloc[-1]["trade_date"] if bars else None
        # JSON 列只收可序列化值：date 以 ISO 字符串进 payload，date 对象进列。
        payload["source_as_of_date"] = as_of_date.isoformat() if as_of_date else None
        self._upsert(db, instrument_id, payload, as_of_date=as_of_date, bars=bars, computed_by=computed_by)
        return payload

    def capture_for_instruments(self, db: Session, instruments: list[Instrument], *, computed_by: str = "scheduled") -> int:
        """为一批标的刷新快照；单标的失败用 SAVEPOINT 隔离，不污染调用方事务。"""
        captured = 0
        for instrument in instruments:
            try:
                with db.begin_nested():
                    self.compute(db, instrument.id, computed_by=computed_by)
                captured += 1
            except Exception as exc:  # noqa: BLE001 - 单标的失败不阻断整批
                logger.warning("sr capture failed for %s: %s", instrument.ts_code, exc)
        return captured

    # -------------------------------------------------------------- 读取

    def latest(self, db: Session, instrument_id: int) -> dict[str, Any] | None:
        snapshot = db.scalar(
            select(SupportResistanceSnapshot)
            .where(SupportResistanceSnapshot.instrument_id == instrument_id, SupportResistanceSnapshot.interval == "1d")
            .order_by(SupportResistanceSnapshot.as_of_date.desc(), SupportResistanceSnapshot.generated_at.desc())
            .limit(1)
        )
        if (snapshot is None or snapshot.method_version != METHOD_VERSION
                or snapshot.config_hash != self.config_hash):
            return None
        frame = self._sr_frame(db, instrument_id)
        if frame.empty or frame.iloc[-1]["trade_date"] != snapshot.as_of_date:
            return None
        payload = dict(snapshot.payload_json or {})
        if payload.get("input_hash") != frame.attrs.get("input_hash"):
            return None
        payload_hash = stable_hash(payload)
        revision_id = _snapshot_revision_id(
            instrument_id=instrument_id,
            as_of_date=snapshot.as_of_date,
            method_version=snapshot.method_version,
            config_hash=snapshot.config_hash,
            price_basis_id=payload.get("price_basis_id"),
            input_hash=payload.get("input_hash"),
            payload_hash=payload_hash,
        )
        revision = db.scalar(select(SupportResistanceSnapshotRevision).where(
            SupportResistanceSnapshotRevision.revision_id == revision_id
        ))
        if (revision is None or revision.payload_hash != payload_hash
                or not _revision_is_self_consistent(revision, expected_revision_id=revision_id)):
            return None
        payload.setdefault("snapshot_as_of_date", snapshot.as_of_date.isoformat())
        payload["revision_id"] = revision_id
        payload["snapshot_source"] = "persisted_snapshot"
        return payload

    def latest_or_compute(self, db: Session, instrument_id: int, *, computed_by: str = "request") -> dict[str, Any]:
        """Compatibility reader: absence requires an explicit task, never GET writes."""
        persisted = self.latest(db, instrument_id)
        if persisted is not None:
            return persisted
        return {**_EMPTY_PAYLOAD, "reason": "snapshot_missing_requires_task", "actionable": False}
