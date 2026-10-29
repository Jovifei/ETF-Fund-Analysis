#!/usr/bin/env python3
"""Derive a candidate list of 沪深300-tracking ETFs for OWNER review.

Zero-credential: reads the public Eastmoney ETF snapshot through the provider
adapter (``fund_etf_spot_em``). This script never freezes the list by itself —
``--confirm --owner`` is required, and the runtime refuses any config whose
``status`` is not ``confirmed``.

Name matching only narrows the candidate list; the owner still reviews every
row. The runtime reads the frozen list and never guesses by name.

Usage (on a machine that can reach eastmoney):

    python scripts/derive_hs300_etf_universe.py
    python scripts/derive_hs300_etf_universe.py --write-config
    python scripts/derive_hs300_etf_universe.py --write-config --confirm --owner jovi

Exit codes: 0 ok, 2 usage error, 3 provider/capability failure.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.providers.base import CapabilityUnavailable, ProviderError  # noqa: E402
from app.providers.factory import create_provider  # noqa: E402
from app.services.hs300_ratio import universe_hash  # noqa: E402

DEFAULT_INDEX = "000300.SH"
DEFAULT_OUTPUT = "deployment_reports/hs300-etf-candidates.json"

# A fund must carry the index name to be considered at all.
INCLUDE_MARKERS = ("沪深300", "HS300")
# Same-index but different exposure: enhanced, feeder, OTC, style or sector
# sub-indices. Excluded candidates stay visible in the report for the owner.
EXCLUDE_MARKERS = (
    "增强", "指增", "联接", "LOF", "价值", "成长", "红利", "低波", "等权",
    "ESG", "质量", "动量", "优选", "精选", "医药", "非银", "银行", "证券",
    "消费", "科技", "信息", "能源", "材料", "工业", "公用", "电信", "A500",
)


def classify(name: str) -> tuple[bool, str]:
    """Return ``(candidate, reason)``. Reasons are printed, never hidden."""
    upper = name.upper()
    if not any(marker.upper() in upper for marker in INCLUDE_MARKERS):
        return False, "not_hs300"
    for marker in EXCLUDE_MARKERS:
        if marker in name:
            return False, f"excluded:{marker}"
    return True, "matched"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Derive HS300 ETF candidates for owner review")
    parser.add_argument("--index-code", default=DEFAULT_INDEX)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--write-config", action="store_true",
                        help="write config/hs300_etf_universe.json (provisional by default)")
    parser.add_argument("--confirm", action="store_true",
                        help="freeze the list as confirmed; requires --write-config and --owner")
    parser.add_argument("--owner", default="", help="owner identifier recorded on confirmation")
    args = parser.parse_args(argv)

    if args.confirm and not args.write_config:
        print(json.dumps({"status": "usage_error", "reason": "--confirm requires --write-config"},
                         ensure_ascii=False))
        return 2
    if args.confirm and not args.owner.strip():
        print(json.dumps({"status": "usage_error", "reason": "--confirm requires --owner"},
                         ensure_ascii=False))
        return 2

    settings = get_settings()
    provider = create_provider(settings)
    try:
        if getattr(provider, "name", "") == "mock":
            print(json.dumps({"status": "refused", "reason": "mock_provider_refused"},
                             ensure_ascii=False))
            return 3
        try:
            catalog = list(provider.fetch_etf_catalog() or [])
        except CapabilityUnavailable as exc:
            print(json.dumps({"status": "unavailable", "reason": type(exc).__name__},
                             ensure_ascii=False))
            return 3
        except ProviderError as exc:
            print(json.dumps({"status": "failed", "reason": type(exc).__name__},
                             ensure_ascii=False))
            return 3
    finally:
        close = getattr(provider, "close", None)
        if callable(close):
            close()

    candidates: list[dict] = []
    rejected: list[dict] = []
    for row in sorted(catalog, key=lambda item: item.ts_code):
        ok, reason = classify(str(row.name))
        entry = {"ts_code": row.ts_code, "name": row.name, "match": reason}
        (candidates if ok else rejected).append(entry)

    funds = sorted({item["ts_code"] for item in candidates})
    digest = universe_hash(args.index_code, funds)
    now = datetime.now(settings.timezone).isoformat()
    confirm = bool(args.confirm)

    report = {
        "status": "confirmed" if confirm else "provisional",
        "index_code": args.index_code,
        "derived_at": now,
        "etf_scanned": len(catalog),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "rejected_count": len(rejected),
        "rejected": rejected,
        "universe_hash": digest,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.write_config:
        payload = {
            "index_code": args.index_code,
            "index_name": "沪深300",
            "definition": "全部跟踪沪深300指数的场内 ETF；不含联接基金、LOF 与指数增强产品。",
            "status": "confirmed" if confirm else "provisional",
            "universe_hash": digest if confirm else None,
            "confirmed_at": now if confirm else None,
            "confirmed_by": args.owner.strip() if confirm else None,
            "derived_by": Path(__file__).name,
            "derived_at": now,
            "funds": funds,
            "notes": [
                "运行期只读本文件，不做名称猜测。",
                "status=confirmed 且 universe_hash 与 funds 完全一致时 Hs300RatioService 才会计算。",
            ],
        }
        target = Path(settings.hs300_universe_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        report["config_written"] = str(target)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
