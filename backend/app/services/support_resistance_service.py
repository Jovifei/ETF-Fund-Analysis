"""支撑/压力唯一计算与读取入口（support-resistance-v1）。

全系统的支撑压力只在这里计算并落库（SupportResistanceSnapshot），
决策总表 / 14:30 工作台 / ETF 详情一律读取快照，禁止各自从日线重算。

统一输入口径（修复方案 P0-5）：
* 回溯窗口 250 个交易日（config 可覆盖）；
* 成交额使用真实 ``amount``，缺失时降级 ``volume * close``（结果可审计）；
* 参数来自 ``config/etf_1430_workbench.json`` 的 ``support_resistance`` 块。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT, Settings, get_settings
from app.models import DailyBar, Instrument, SupportResistanceSnapshot
from app.utils.hashing import stable_hash
from app.utils.support_resistance import build_support_resistance

logger = logging.getLogger(__name__)

METHOD_VERSION = "support-resistance-v1"
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
        """统一输入口径：最近 ``window`` 根日线 + 真实成交额（缺失时 volume*close）。"""
        rows = db.scalars(
            select(DailyBar)
            .where(DailyBar.instrument_id == instrument_id)
            .order_by(DailyBar.trade_date.desc())
            .limit(window)
        ).all()
        rows = list(reversed(rows))
        if not rows:
            return pd.DataFrame()
        records = []
        for row in rows:
            amount = row.amount
            if amount in (None, 0) or not amount:
                close = row.close
                volume = row.volume
                amount = float(close) * float(volume) if close and volume else 0.0
            records.append(
                {
                    "trade_date": row.trade_date,
                    "open": row.open,
                    "high": row.high,
                    "low": row.low,
                    "close": row.close,
                    "volume": row.volume or 0.0,
                    "amount": amount,
                }
            )
        return pd.DataFrame(records)

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
        """计算 + 落库 + 返回 payload（调度器/请求兜底共用同一口径）。"""
        frame = self._sr_frame(db, instrument_id)
        bars = len(frame)
        payload = build_support_resistance(frame, self.config)
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
        if snapshot is None:
            return None
        payload = dict(snapshot.payload_json or {})
        payload.setdefault("snapshot_as_of_date", snapshot.as_of_date.isoformat())
        payload["snapshot_source"] = "persisted_snapshot"
        return payload

    def latest_or_compute(self, db: Session, instrument_id: int, *, computed_by: str = "request") -> dict[str, Any]:
        """读取持久化快照；缺失时即时计算并尝试落库（只读请求里 flush 不提交也无妨）。"""
        persisted = self.latest(db, instrument_id)
        if persisted is not None:
            return persisted
        return self.compute(db, instrument_id, computed_by=computed_by)
