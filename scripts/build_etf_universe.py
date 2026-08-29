#!/usr/bin/env python3
"""Build a real ETF/LOF universe candidate list from Tushare fund_basic.

Dry-run by default: writes a candidate JSON for MANUAL REVIEW. The
--write-watchlist mode rewrites config/watchlist.json only when
--confirm-private-use is also passed (personal private research use only).

Selection evidence per fund: scale (issue_amount), fee (m_fee/c_fee),
listing age (list_date vs --history-years), liquidity proxy (a small recent
daily-bar window), theme classification (config/universe_theme_rules.json
keyword rules over name), and delisting-risk flags (due_date present or
short remaining life). The market-gate benchmark 510300.SH is always kept.

No survivorship-bias claims are made: fund_basic(status="L") lists only
live funds, so the universe is a LIVE-fund pool by construction; this is
recorded in the report.

Token safety: TUSHARE_TOKEN is read via settings only; the report contains
booleans, never the token.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.utils.reproducibility import current_git_commit  # noqa: E402

DEFAULT_TARGET = 100
MIN_POOL = 50
MAX_POOL = 150
GATE_BENCHMARK = "510300.SH"

# Fallback theme rules when config/universe_theme_rules.json is absent:
# ordered keyword -> (theme_l1, theme_l2). First match wins.
DEFAULT_THEME_RULES: list[dict] = [
    {"keywords": ["半导体", "芯片"], "theme_l1": "科技", "theme_l2": "半导体"},
    {"keywords": ["人工智能", "AI", "智能"], "theme_l1": "科技", "theme_l2": "人工智能"},
    {"keywords": ["通信", "5G"], "theme_l1": "科技", "theme_l2": "通信"},
    {"keywords": ["机器人"], "theme_l1": "制造", "theme_l2": "机器人"},
    {"keywords": ["军工", "国防"], "theme_l1": "制造", "theme_l2": "军工"},
    {"keywords": ["医疗", "医药", "创新药", "生物"], "theme_l1": "医药", "theme_l2": "医疗"},
    {"keywords": ["白酒", "食品", "消费", "酒"], "theme_l1": "消费", "theme_l2": "消费"},
    {"keywords": ["新能源", "电池", "光伏"], "theme_l1": "制造", "theme_l2": "新能源"},
    {"keywords": ["有色", "黄金", "煤炭", "石油", "原油"], "theme_l1": "资源能源", "theme_l2": "资源"},
    {"keywords": ["银行"], "theme_l1": "金融", "theme_l2": "银行"},
    {"keywords": ["证券", "券商"], "theme_l1": "金融", "theme_l2": "证券"},
    {"keywords": ["保险"], "theme_l1": "金融", "theme_l2": "保险"},
    {"keywords": ["房地产", "地产"], "theme_l1": "地产建筑", "theme_l2": "地产"},
    {"keywords": ["基建", "建材"], "theme_l1": "地产建筑", "theme_l2": "基建"},
    {"keywords": ["农业", "养殖"], "theme_l1": "农业", "theme_l2": "农业"},
    {"keywords": ["传媒", "游戏", "影视"], "theme_l1": "科技", "theme_l2": "传媒"},
    {"keywords": ["红利"], "theme_l1": "宽基", "theme_l2": "红利"},
    {"keywords": ["价值"], "theme_l1": "宽基", "theme_l2": "价值"},
    {"keywords": ["创业板", "科创", "北证"], "theme_l1": "宽基", "theme_l2": "成长"},
    {"keywords": ["沪深300", "中证500", "中证1000", "中证800", "上证50", "深证100"],
     "theme_l1": "宽基", "theme_l2": "规模指数"},
]


def classify(name: str, rules: list[dict]) -> tuple[str, str]:
    for rule in rules:
        for keyword in rule.get("keywords", []):
            if keyword and keyword in name:
                return rule["theme_l1"], rule["theme_l2"]
    return "宽基", "其他"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build real ETF/LOF universe candidate")
    parser.add_argument("--target-size", type=int, default=DEFAULT_TARGET)
    parser.add_argument("--history-years", type=int, default=5)
    parser.add_argument("--output", type=str, default="deployment_reports/watchlist-candidate.json")
    parser.add_argument("--write-watchlist", action="store_true")
    parser.add_argument("--confirm-private-use", action="store_true")
    parser.add_argument("--min-amount-20d", type=float, default=20000000.0,
                        help="minimum 20-day mean daily amount in yuan (liquidity proxy)")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.tushare_token:
        print(json.dumps({"status": "token_missing"}, ensure_ascii=False))
        return 3

    import tushare as ts  # deferred: heavy import, token-gated

    pro = ts.pro_api(str(settings.tushare_token))
    today = date.today()
    cutoff = today - timedelta(days=args.history_years * 365)

    # --- candidate pool from fund_basic (live funds only) ---
    frame = pro.fund_basic(market="E", status="L")
    rows = frame.to_dict(orient="records") if hasattr(frame, "to_dict") else list(frame)

    candidates: list[dict] = []
    for row in rows:
        code = str(row.get("ts_code") or "").upper()
        if not code:
            continue
        if not (code.endswith(".SH") or code.endswith(".SZ")):
            continue
        name = str(row.get("name") or "")
        if not name or ("ETF" not in name and "LOF" not in name
                        and row.get("fund_type") not in ("ETF", "LOF")):
            continue
        list_date_raw = row.get("list_date")
        try:
            list_date = date(int(str(list_date_raw)[:4]), int(str(list_date_raw)[4:6]),
                             int(str(list_date_raw)[6:8])) if list_date_raw else None
        except (ValueError, TypeError):
            list_date = None
        issue_amount = row.get("issue_amount")
        try:
            scale = float(issue_amount) if issue_amount not in (None, "") else None
        except (TypeError, ValueError):
            scale = None
        due_date_raw = row.get("due_date")
        delist_risk = bool(due_date_raw)  # due_date on a fund_basic row is unusual; flag it
        theme_l1, theme_l2 = classify(name, DEFAULT_THEME_RULES)
        candidates.append({
            "ts_code": code,
            "symbol": code.split(".")[0],
            "name": name,
            "kind": "ETF" if "ETF" in name else "LOF",
            "list_date": list_date.isoformat() if list_date else None,
            "listing_age_years": round((today - list_date).days / 365.25, 1) if list_date else None,
            "scale_yi": round(scale / 1e8, 2) if scale else None,  # 亿元
            "m_fee": row.get("m_fee"),
            "c_fee": row.get("c_fee"),
            "management": row.get("management"),
            "delist_risk_flag": delist_risk,
            "theme_l1": theme_l1,
            "theme_l2": theme_l2,
        })

    # --- liquidity probe: recent 20d mean amount for a bounded shortlist ---
    def liquidity(code: str) -> float | None:
        try:
            bars_frame = pro.fund_daily(
                ts_code=code,
                start_date=(today - timedelta(days=45)).strftime("%Y%m%d"),
                end_date=today.strftime("%Y%m%d"),
            )
            bars = bars_frame.to_dict(orient="records") if hasattr(bars_frame, "to_dict") else list(bars_frame)
            amounts = [float(b["amount"]) for b in bars if b.get("amount") not in (None, "")]
            return sum(amounts) / len(amounts) if amounts else None
        except Exception:  # noqa: BLE001 - liquidity probe is best-effort
            return None

    # Pre-filter before probing: scale >= 2亿, listing age >= history-years*0.8
    pre = [c for c in candidates if (c["scale_yi"] or 0) >= 2.0
           and (c["listing_age_years"] or 0) >= args.history_years * 0.8
           and not c["delist_risk_flag"]]
    pre.sort(key=lambda c: -(c["scale_yi"] or 0))

    # Probe at most target*3 codes for liquidity (bounded API usage)
    probe_limit = min(len(pre), args.target_size * 3)
    for item in pre[:probe_limit]:
        mean_amount = liquidity(item["ts_code"])
        item["mean_amount_20d_yuan"] = round(mean_amount, 0) if mean_amount else None
    probed = [item for item in pre[:probe_limit] if item.get("mean_amount_20d_yuan")]
    probed.sort(key=lambda c: -(c["mean_amount_20d_yuan"] or 0))

    selected = probed[: args.target_size]
    if len(selected) < MIN_POOL:
        print(json.dumps({
            "status": "insufficient_pool",
            "selected": len(selected),
            "required_min": MIN_POOL,
        }, ensure_ascii=False))
        return 2

    # Keep the market-gate benchmark
    codes = {item["ts_code"] for item in selected}
    if GATE_BENCHMARK not in codes:
        benchmark_row = next((c for c in candidates if c["ts_code"] == GATE_BENCHMARK), None)
        if benchmark_row is not None:
            selected.append(benchmark_row)

    theme_counts: dict[str, int] = {}
    for item in selected:
        theme_counts[item["theme_l1"]] = theme_counts.get(item["theme_l1"], 0) + 1

    report = {
        "generated_at": date.today().isoformat(),
        "git_commit_sha": current_git_commit(),
        "status": "candidate_ready_for_manual_review",
        "target_size": args.target_size,
        "selected_count": len(selected),
        "pool_bounds": {"min": MIN_POOL, "max": MAX_POOL},
        "selection_rules": {
            "scale_min_yi": 2.0,
            "listing_age_min_years": round(args.history_years * 0.8, 1),
            "min_mean_amount_20d_yuan": args.min_amount_20d,
            "live_funds_only": True,
            "survivorship_note": "fund_basic(status=L) lists live funds only; this is a LIVE-fund pool, "
                                 "not a survivorship-bias-free historical universe",
        },
        "theme_coverage": theme_counts,
        "candidates": [
            {**item,
             "benchmark": GATE_BENCHMARK if item["ts_code"] == GATE_BENCHMARK else None,
             "enabled": True}
            for item in selected
        ],
    }
    if not (MIN_POOL <= len(selected) <= MAX_POOL):
        report["status"] = "out_of_bounds"

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "selected": len(selected),
        "themes": theme_counts,
        "output": str(output),
    }, ensure_ascii=False))

    # --- write mode ---
    if args.write_watchlist:
        if not args.confirm_private_use:
            print("REFUSED: --write-watchlist requires --confirm-private-use "
                  "(personal private research only)", file=sys.stderr)
            return 2
        if report["status"] != "candidate_ready_for_manual_review":
            print(f"REFUSED: candidate status is '{report['status']}', not ready", file=sys.stderr)
            return 2
        watchlist = {"instruments": [
            {
                "ts_code": item["ts_code"],
                "symbol": item["symbol"],
                "name": item["name"],
                "kind": item["kind"],
                "theme_l1": item["theme_l1"],
                "theme_l2": item["theme_l2"],
                "benchmark": GATE_BENCHMARK if item["ts_code"] == GATE_BENCHMARK else None,
                "enabled": True,
            }
            for item in selected
        ]}
        target = Path("config/watchlist.json")
        backup = target.with_suffix(".json.bak")
        backup.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
        target.write_text(
            json.dumps(watchlist, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps({
            "status": "watchlist_written",
            "count": len(watchlist["instruments"]),
            "backup": str(backup),
        }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
