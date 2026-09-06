"""Catalog capability adapter. Source calls live here, not in API/business views.

A full catalog does not automatically enroll every instrument in the compute
universe. Only exchange-listed ETF/LOF identities supported by the source are
accepted; unknown classifications are never guessed to be ETF.
"""
from __future__ import annotations

import re

from app.providers.base import CapabilityUnavailable, ProviderError
from app.providers.types import InstrumentRecord


def catalog_records(provider) -> list[InstrumentRecord]:
    if getattr(provider, "name", "") == "composite":
        return provider._invoke("list_etf_catalog", catalog_records)
    name = getattr(provider, "name", "")
    if name in {"mock", "ftshare"}:
        return provider.list_instruments()
    result = []
    if name == "akshare":
        failures = []
        for kind, function in (("ETF", "fund_etf_spot_em"), ("LOF", "fund_lof_spot_em")):
            try:
                rows = provider._records(getattr(provider.ak, function)())
            except Exception as exc:
                failures.append(type(exc).__name__)
                continue
            for row in rows:
                symbol = str(row.get("代码") or row.get("基金代码") or "").strip()
                title = str(row.get("名称") or row.get("基金简称") or "").strip()
                if not re.fullmatch(r"[15]\d{5}", symbol) or not title:
                    continue
                exchange = "SH" if symbol.startswith("5") else "SZ"
                result.append(InstrumentRecord(ts_code=f"{symbol}.{exchange}", symbol=symbol, name=title[:128], kind=kind, exchange=exchange, enabled=False, metadata={"catalog_source": f"akshare:{function}", "catalog_only": True}))
    elif name == "tushare":
        rows = provider._records(provider.pro.fund_basic(market="E", status="L"))
        for row in rows:
            code = str(row.get("ts_code") or "").upper()
            title = str(row.get("name") or "").strip()
            kind = "ETF" if "ETF" in title.upper() else "LOF" if "LOF" in title.upper() else None
            if not kind or not re.fullmatch(r"\d{6}\.(SH|SZ)", code):
                continue
            result.append(InstrumentRecord(ts_code=code, symbol=code[:6], name=title[:128], kind=kind, exchange=code[-2:], enabled=False, metadata={"catalog_source": "tushare:fund_basic:E:L", "catalog_only": True, "list_date": row.get("list_date")}))
    else:
        raise CapabilityUnavailable("ETF catalog not supported")
    if not result:
        raise ProviderError("ETF catalog returned no usable records")
    if len(result) > 10000:
        raise ProviderError("ETF catalog exceeds safety bound")
    seen = {}
    for row in result:
        if row.ts_code in seen and (seen[row.ts_code].name, seen[row.ts_code].kind) != (row.name, row.kind):
            raise ProviderError("ETF catalog contains conflicting identities")
        seen[row.ts_code] = row
    return list(seen.values())
