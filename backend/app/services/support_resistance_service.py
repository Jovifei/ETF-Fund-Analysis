"""支撑/压力唯一计算与读取入口（support-resistance-v3-research-price-basis）。

全系统的支撑压力只在这里计算并落库（SupportResistanceSnapshot），
决策总表 / 14:30 工作台 / ETF 详情一律读取快照，禁止各自从日线重算。

统一输入口径（修复方案 P0-5）：
* 回溯窗口 250 根已存日线；按统一公司行为研究口径计算，原始行情不改写；
* 保留真实 ``amount/volume`` 的空值与零值，不估算或填零；
* 参数来自 ``config/etf_1430_workbench.json`` 的 ``support_resistance`` 块。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT, Settings, get_settings
from app.models import DailyBar, Instrument, SupportResistanceSnapshot
from app.utils.hashing import stable_hash
from app.utils.support_resistance import build_support_resistance

logger = logging.getLogger(__name__)

METHOD_VERSION = "support-resistance-v3-research-price-basis"
DEFAULT_WINDOW = 250

_EMPTY_PAYLOAD: dict[str, Any] = {
    "qualified": False,
    "reason": "history_too_short",
    "levels": [],
    "nearest_support": None,
    "nearest_resistance": None,
    "trend_lines": [],
    "chan_zone_approx": None,
}


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

    def _sr_frame(self, db: Session, instrument_id: int, *, window: int = DEFAULT_WINDOW) -> pd.DataFrame:
        """Bounded research history; unknown units may not feed weighted methods."""
        from app.providers.corporate_action_contract import official_corporate_actions, research_history_rows
        from app.providers.data_contract import finite, price_history_issue, row_units_verified
        from app.utils.input_lineage import history_digest
        rows = list(reversed(db.scalars(select(DailyBar)
            .where(DailyBar.instrument_id == instrument_id)
            .order_by(DailyBar.trade_date.desc(), DailyBar.id.desc()).limit(window)).all()))
        instrument = db.get(Instrument, instrument_id)
        research_rows = rows if self.settings.market_provider == "mock" or instrument is None else research_history_rows(rows, instrument.ts_code)
        adjustments = {row.adjust for row in rows}
        split_evidence = (
            [event.evidence_id for event in official_corporate_actions(instrument.ts_code)]
            if instrument is not None and adjustments == {"none"} and self.settings.market_provider != "mock"
            else []
        )
        basis_id = stable_hash({"instrument": instrument.ts_code if instrument else instrument_id,
                                "adjustments": sorted(adjustments), "split_evidence": split_evidence,
                                "method_version": METHOD_VERSION})
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
        frame.attrs["price_basis_id"] = basis_id
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

    def compute(self, db: Session, instrument_id: int, *, computed_by: str = "scheduled") -> dict[str, Any]:
        """显式任务计算并落库；页面读取不触发本方法。"""
        frame = self._sr_frame(db, instrument_id)
        bars = len(frame)
        issue = frame.attrs.get("history_issue")
        payload = ({**_EMPTY_PAYLOAD, "reason": issue} if issue
                   else build_support_resistance(frame, self.config))
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
        payload.setdefault("snapshot_as_of_date", snapshot.as_of_date.isoformat())
        payload["snapshot_source"] = "persisted_snapshot"
        return payload

    def latest_or_compute(self, db: Session, instrument_id: int, *, computed_by: str = "request") -> dict[str, Any]:
        """Compatibility reader: absence requires an explicit task, never GET writes."""
        persisted = self.latest(db, instrument_id)
        if persisted is not None:
            return persisted
        return {**_EMPTY_PAYLOAD, "reason": "snapshot_missing_requires_task", "actionable": False}
