#!/usr/bin/env python3
"""Generate one immutable ETF 14:30 research report.

This script does not place orders and does not print credentials.
It refreshes sector snapshots first (optional; failure degrades to empty
sector columns without blocking the report).
"""

from __future__ import annotations

import json
import logging

from app.core.config import get_settings
from app.db.session import session_scope
from app.providers.factory import create_provider
from app.services.etf_1430_service import ETF1430WorkbenchService
from app.services.market_service import MarketService

logger = logging.getLogger(__name__)


def _refresh_sector_snapshots(settings) -> None:
    """可选：回填板块涨跌家数。失败仅记录日志，不阻断报告生成。"""
    try:
        provider = create_provider(settings)
        try:
            with session_scope() as db:
                market = MarketService(provider, settings, persist_provider_audits=False)
                market.refresh_sector_snapshots(db, run_id="etf-1430-daily")
        finally:
            close = getattr(provider, "close", None)
            if callable(close):
                close()
    except Exception as exc:
        logger.warning("sector snapshot refresh skipped (report still generated): %s", exc)


def main() -> int:
    settings = get_settings()
    _refresh_sector_snapshots(settings)
    with session_scope() as db:
        result = ETF1430WorkbenchService(settings).generate_report(db)
    print(json.dumps({key: result[key] for key in ("status", "filename", "generated_at", "instrument_count", "research_only")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
