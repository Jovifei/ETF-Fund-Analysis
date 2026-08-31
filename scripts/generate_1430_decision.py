#!/usr/bin/env python3
"""Generate one immutable ETF 14:30 research report.

This script does not place orders and does not print credentials.
"""

from __future__ import annotations

import json

from app.core.config import get_settings
from app.db.session import session_scope
from app.services.etf_1430_service import ETF1430WorkbenchService


def main() -> int:
    settings = get_settings()
    with session_scope() as db:
        result = ETF1430WorkbenchService(settings).generate_report(db)
    print(json.dumps({key: result[key] for key in ("status", "filename", "generated_at", "instrument_count", "research_only")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
