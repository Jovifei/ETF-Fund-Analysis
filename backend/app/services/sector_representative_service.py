"""Sector and Index to Representative ETF mapping service (P2).

Provides verified, bounded, in-window mappings from sectors/themes/indices
to representative liquid ETFs (e.g. Huatai-PineBridge, China Southern, etc.).
Never guesses unverified tickers, enforces explicit validity periods (effective_from/to),
and guarantees research-only semantics.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

CONFIG_FILE = Path(__file__).resolve().parents[3] / "config" / "sector_representative_etf_map.json"
SHANGHAI = ZoneInfo("Asia/Shanghai")


def _to_date(val: Any) -> date | None:
    if val is None:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.astimezone(SHANGHAI).date() if val.tzinfo else val.date()
    try:
        s = str(val).strip()[:10]
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


@lru_cache(maxsize=1)
def load_representative_etf_config() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        return {"schema_version": "sector_representative_map_v1", "mappings": []}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"schema_version": "sector_representative_map_v1", "mappings": []}


def clear_representative_etf_cache() -> None:
    load_representative_etf_config.cache_clear()


class SectorRepresentativeService:
    def __init__(self, config_dict: dict[str, Any] | None = None) -> None:
        self._cfg = config_dict or load_representative_etf_config()
        self._mappings: list[dict[str, Any]] = self._cfg.get("mappings", [])

    def list_mappings(self, *, as_of: str | date | datetime | None = None) -> list[dict[str, Any]]:
        """Return all valid mappings within the requested as_of window."""
        as_of_d = _to_date(as_of) or datetime.now(SHANGHAI).date()
        result = []
        for m in self._mappings:
            if m.get("status") != "active":
                continue
            eff_from = _to_date(m.get("effective_from"))
            eff_to = _to_date(m.get("effective_to"))
            if eff_from and as_of_d < eff_from:
                continue
            if eff_to and as_of_d > eff_to:
                continue
            result.append(dict(m))
        return result

    def resolve_representative(
        self,
        *,
        sector_name: str | None = None,
        theme_l1: str | None = None,
        theme_l2: str | None = None,
        index_code: str | None = None,
        as_of: str | date | datetime | None = None,
    ) -> dict[str, Any] | None:
        """Resolve a sector or index to its representative ETF.

        Lookup precedence:
        1. Exact index code match.
        2. Exact sector_name match.
        3. Exact theme_l2 match.
        4. Substring in sector_name.
        5. Theme_l1 match.
        """
        valid_items = self.list_mappings(as_of=as_of)
        if not valid_items:
            return None

        clean_sector = str(sector_name or "").strip()
        clean_l1 = str(theme_l1 or "").strip()
        clean_l2 = str(theme_l2 or "").strip()
        clean_idx = str(index_code or "").strip().upper()

        # 1. Exact index code match
        if clean_idx:
            for item in valid_items:
                idx_info = item.get("tracking_index") or {}
                if str(idx_info.get("code") or "").strip().upper() == clean_idx:
                    return item

        # 2. Exact sector_name match
        if clean_sector:
            for item in valid_items:
                if str(item.get("sector_name") or "").strip() == clean_sector:
                    return item

        # 3. Exact theme_l2 match
        if clean_l2:
            for item in valid_items:
                if str(item.get("theme_l2") or "").strip() == clean_l2:
                    return item

        # 4. Substring in sector_name
        if clean_sector:
            for item in valid_items:
                name = str(item.get("sector_name") or "").strip()
                if name and (name in clean_sector or clean_sector in name):
                    return item

        # 5. Theme_l1 match
        if clean_l1:
            for item in valid_items:
                if str(item.get("theme_l1") or "").strip() == clean_l1:
                    return item

        return None
