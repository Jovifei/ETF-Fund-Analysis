"""用户自选关注服务（修复方案 PR-D）。

职责：
* 代码规范化与上游解析（Provider Adapter 的 ``resolve_instrument``，禁止业务层直连行情站）；
* 全局 ``Instrument`` 缺失时按用户确认的解析结果入库（主题由 universe_theme_rules 分类）；
* 用户关注条目的增删查（user-scoped；user_id=None 表示系统/匿名池）。

边界：本服务不拉历史、不计算指标（新标的的日线/指标由既有同步管线在
后续任务中补齐）；不写 Holding（由用户在关注条目上显式转为持仓）。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT, Settings, get_settings
from app.models import Instrument, UserWatchlistEntry
from app.providers.base import MarketProvider
from app.utils.hashing import stable_hash

logger = logging.getLogger(__name__)

_CODE_RULES_PATH = PROJECT_ROOT / "config" / "universe_theme_rules.json"

_FALLBACK_RULES: list[dict[str, Any]] = [
    {"keywords": ["半导体", "芯片"], "theme_l1": "科技", "theme_l2": "半导体"},
    {"keywords": ["医药", "医疗", "创新药", "生物"], "theme_l1": "医药", "theme_l2": "医疗"},
    {"keywords": ["黄金", "有色", "煤炭", "石油"], "theme_l1": "资源能源", "theme_l2": "资源"},
    {"keywords": ["银行", "证券", "保险", "券商"], "theme_l1": "金融", "theme_l2": "金融"},
    {"keywords": ["军工", "国防", "机器人"], "theme_l1": "制造", "theme_l2": "制造"},
    {"keywords": ["酒", "食品", "消费"], "theme_l1": "消费", "theme_l2": "消费"},
]


def load_theme_rules() -> list[dict[str, Any]]:
    if not _CODE_RULES_PATH.is_file():
        return _FALLBACK_RULES
    try:
        rules = json.loads(_CODE_RULES_PATH.read_text(encoding="utf-8")).get("rules", [])
        return list(rules) if isinstance(rules, list) else _FALLBACK_RULES
    except (OSError, ValueError):
        return _FALLBACK_RULES


def classify_theme(name: str) -> tuple[str, str]:
    """按 universe_theme_rules 关键词分类；未命中归入 宽基/其他。"""
    for rule in load_theme_rules():
        for keyword in rule.get("keywords", []):
            if keyword and keyword in name:
                return rule.get("theme_l1", "宽基"), rule.get("theme_l2", "其他")
    return "宽基", "其他"


class WatchlistError(ValueError):
    """带用户可读消息的自选操作失败。"""


class WatchlistService:
    def __init__(self, settings: Settings | None = None, provider: MarketProvider | None = None) -> None:
        self.settings = settings or get_settings()
        self.provider = provider
        self.rules_version = stable_hash({"rules": load_theme_rules()})[:12]

    # ------------------------------------------------------------------ add

    def add(self, db: Session, *, code: str, note: str | None = None, user_id: int | None = None) -> dict[str, Any]:
        cleaned = (code or "").strip().upper()
        if not cleaned:
            raise WatchlistError("请输入 ETF/LOF 代码")
        instrument = self._resolve_or_create(db, cleaned)
        existing = db.scalar(
            select(UserWatchlistEntry).where(
                UserWatchlistEntry.user_id == user_id,
                UserWatchlistEntry.instrument_id == instrument.id,
            )
        )
        if existing is not None:
            return self._entry_view(db, existing, duplicate=True)
        entry = UserWatchlistEntry(user_id=user_id, instrument_id=instrument.id, note=note)
        db.add(entry)
        db.flush()
        logger.info("watchlist entry added: user=%s code=%s", user_id, instrument.ts_code)
        return self._entry_view(db, entry, duplicate=False)

    def _resolve_or_create(self, db: Session, cleaned: str) -> Instrument:
        existing = db.scalar(select(Instrument).where(Instrument.ts_code == cleaned))
        if existing is None and "." not in cleaned:
            # 6 位 symbol：先按已入库 symbol 找
            existing = db.scalar(select(Instrument).where(Instrument.symbol == cleaned))
        if existing is not None:
            return existing

        record = self.provider.resolve_instrument(cleaned) if self.provider is not None else None
        if record is None:
            raise WatchlistError(
                "未能从数据源识别该代码；请确认是场内 ETF/LOF，或使用完整代码（如 512480.SH）"
            )
        theme_l1, theme_l2 = classify_theme(record.name)
        instrument = Instrument(
            ts_code=record.ts_code,
            symbol=record.symbol,
            name=record.name,
            kind=record.kind or "ETF",
            exchange=record.exchange,
            theme_l1=record.theme_l1 or theme_l1,
            theme_l2=record.theme_l2 or theme_l2,
            enabled=True,
            metadata_json={
                "user_added": True,
                "theme_rules_version": self.rules_version,
                **(record.metadata or {}),
            },
        )
        db.add(instrument)
        db.flush()
        return instrument

    # ----------------------------------------------------------- list/delete

    def list_entries(self, db: Session, *, user_id: int | None = None) -> list[dict[str, Any]]:
        entries = db.scalars(
            select(UserWatchlistEntry)
            .where(UserWatchlistEntry.user_id == user_id)
            .order_by(UserWatchlistEntry.id.desc())
        ).all()
        return [self._entry_view(db, entry) for entry in entries]

    def delete(self, db: Session, entry_id: int, *, user_id: int | None = None) -> bool:
        entry = db.get(UserWatchlistEntry, entry_id)
        if entry is None or entry.user_id != user_id:
            return False
        db.delete(entry)
        db.flush()
        return True

    # ------------------------------------------------------------------ view

    def _entry_view(self, db: Session, entry: UserWatchlistEntry, *, duplicate: bool = False) -> dict[str, Any]:
        instrument = db.get(Instrument, entry.instrument_id)
        return {
            "id": entry.id,
            "ts_code": instrument.ts_code if instrument else None,
            "name": instrument.name if instrument else None,
            "theme_l1": instrument.theme_l1 if instrument else None,
            "note": entry.note,
            "duplicate": duplicate,
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
        }
