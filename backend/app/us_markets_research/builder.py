"""Build the ``us_markets_research`` part, history levels and an audit trail."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from app.us_markets_research.compute import clean, equal_weight_basket, series_entry
from app.us_markets_research.contracts import PART_NAME, SCHEMA_VERSION, validate_part
from app.us_markets_research.providers import CLOSE_SOURCE_PROVISIONAL, DailyProvider

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "us_markets_research.json"
SOURCE_NOTE = ("篮子与指数日线来自所列数据源的复权收盘价，是研究口径；"
               "生产环境官方美股指数卡片仍使用原有新浪通道，本区块不替代它。")


@dataclass
class BuildResult:
    part: dict[str, Any]
    history: pd.DataFrame
    audit: list[dict[str, Any]]
    problems: list[str]


def load_config(path: Path | str = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    raw = Path(path).read_bytes()
    config = json.loads(raw.decode("utf-8"))
    config["_sha256"] = hashlib.sha256(raw).hexdigest()
    if config.get("actionable") is not False or config.get("research_only") is not True:
        raise ValueError("us_markets_research config must be research_only and actionable=false")
    return config


def required_tickers(config: dict[str, Any]) -> list[str]:
    tickers: list[str] = []
    for basket in config["baskets"]:
        tickers.extend(basket["members"])
    tickers.extend(item["yahoo_symbol"] for item in config["indices"])
    return list(dict.fromkeys(tickers))


def build(config: dict[str, Any], provider: DailyProvider, *, today: date | None = None,
          as_of: date | None = None, now: datetime | None = None) -> BuildResult:
    """Fetch, compose and validate. ``as_of`` truncates data (reproducible backfills)."""
    today = today or datetime.now(timezone.utc).date()
    now = now or datetime.now(timezone.utc)
    start = date.fromisoformat(config["start_date"])
    end = (as_of or today) + timedelta(days=1)
    tickers = required_tickers(config)
    fetched = provider.fetch(tickers, start, end)
    frames = {t: (f[f.index <= pd.Timestamp(as_of)] if as_of else f) for t, f in fetched.frames.items()}
    frames = {t: f for t, f in frames.items() if not f.empty}
    min_members = int(config.get("min_basket_members", 3))
    source_label = fetched.source_label
    index_close = {item["benchmark_role"]: frames[item["yahoo_symbol"]]["close"]
                   for item in config["indices"] if item.get("benchmark_role") and item["yahoo_symbol"] in frames}
    series: list[dict[str, Any]] = []
    history_parts: list[pd.DataFrame] = []

    def bench_for(series_id: str) -> dict[str, pd.Series]:
        own = {item["benchmark_role"] for item in config["indices"] if item["series_id"] == series_id}
        return {role: s for role, s in index_close.items() if role not in own}

    for basket in config["baskets"]:
        members = basket["members"]
        df, meta = equal_weight_basket(frames, members, min_members)
        if df.empty:
            series.append(_unavailable(basket, kind="basket", reason=meta.get("error", "no_data"), meta=meta))
            continue
        extra = {"members": _member_rows(config, frames, members, meta), "weighting": config.get("weighting"),
                 "rationale": basket["rationale"], "official_index": False,
                 "coverage_note": _coverage_note(meta, members)}
        entry = series_entry(series_id=basket["series_id"], label=basket["label"], group_id=basket["group_id"],
                             kind="basket", df=df, with_volume=False, benchmarks=bench_for(basket["series_id"]),
                             source_label=source_label, extra=extra)
        series.append(entry)
        history_parts.append(_history(basket["series_id"], df))
    for item in config["indices"]:
        frame = frames.get(item["yahoo_symbol"])
        if frame is None:
            series.append(_unavailable(item, kind="index", reason="provider_returned_no_data", meta={}))
            continue
        df = frame.assign(provisional=frame["close_source"] == CLOSE_SOURCE_PROVISIONAL)
        extra = {"official_index": True, "market_context_id": item.get("market_context_id"),
                 "coverage_note": "官方指数；此处为研究对照序列，首页指数卡片读数以原有新浪通道为准。"}
        series.append(series_entry(series_id=item["series_id"], label=item["label"], group_id=item["group_id"],
                                   kind="index", df=df, with_volume=True, benchmarks=bench_for(item["series_id"]),
                                   source_label=source_label, extra=extra))
        history_parts.append(_history(item["series_id"], df))

    available = [s for s in series if s.get("available")]
    dates = [s["as_of"] for s in available]
    availability = "unavailable" if not available else ("available" if len(available) == len(series) else "partial")
    part: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION, "research_only": True, "actionable": False, "changes_grade": False,
        "calibration_status": "not_calibrated", "availability": availability,
        "as_of": max(dates) if dates else None,
        "generated_at": now.astimezone(timezone.utc).isoformat(),
        "config_version": config["config_version"], "config_sha256": config["_sha256"],
        "source": {"label": source_label, "version": fetched.source_version,
                   "provider": getattr(provider, "name", "unknown"), "note": SOURCE_NOTE},
        "disclaimer": config["disclaimer"],
        "weighting": config.get("weighting"),
        "provisional_closes": fetched.provisional,
        "failed_tickers": sorted({a["ticker"] for a in fetched.audit if not a["ok"] and a.get("ticker")}),
        "groups": config["groups"], "series": series,
    }
    problems = validate_part(part)
    history = pd.concat(history_parts) if history_parts else pd.DataFrame()
    return BuildResult(part=part, history=history, audit=fetched.audit, problems=problems)


def _history(series_id: str, df: pd.DataFrame) -> pd.DataFrame:
    out = df[["open", "high", "low", "close"]].copy()
    out.insert(0, "series_id", series_id)
    out["provisional"] = df["provisional"] if "provisional" in df.columns else False
    out.index.name = "date"
    return out.reset_index()


def _unavailable(item: dict[str, Any], *, kind: str, reason: str, meta: dict[str, Any]) -> dict[str, Any]:
    return {"series_id": item["series_id"], "label": item["label"], "group_id": item["group_id"], "kind": kind,
            "available": False, "reason": reason, "as_of": None, "missing_members": meta.get("missing_members", []),
            "research_only": True, "actionable": False, "calibration_status": "not_calibrated"}


def _member_rows(config: dict[str, Any], frames: dict[str, pd.DataFrame], members: list[str],
                 meta: dict[str, Any]) -> list[dict[str, Any]]:
    from app.us_markets_research.compute import period_return, ytd_return
    rows = []
    for ticker in members:
        frame = frames.get(ticker)
        presence = meta.get("presence", {}).get(ticker, {})
        if frame is None or frame.empty:
            rows.append({"ticker": ticker, "name": config["member_names"].get(ticker, ticker), "available": False})
            continue
        close = frame["close"]
        rows.append({
            "ticker": ticker, "name": config["member_names"].get(ticker, ticker), "available": True,
            "first_date": presence.get("first"), "as_of": presence.get("last"),
            "provisional_last_close": bool(frame["close_source"].iloc[-1] == CLOSE_SOURCE_PROVISIONAL),
            "returns": {"1w": clean(period_return(close, 5)), "1m": clean(period_return(close, 21)),
                        "3m": clean(period_return(close, 63)), "ytd": clean(ytd_return(close))},
        })
    return rows


def _coverage_note(meta: dict[str, Any], members: list[str]) -> str | None:
    missing = meta.get("missing_members") or []
    late = [f"{m} 自 {p['first']}" for m, p in meta.get("presence", {}).items()
            if p.get("first") and p["first"] > "2018-02-01"]
    parts = []
    if late:
        parts.append("成分按上市日起逐步扩容：" + "、".join(late))
    if missing:
        parts.append("本次缺少成分：" + "、".join(missing))
    return "；".join(parts) or None


def write_outputs(result: BuildResult, out_dir: Path | str) -> dict[str, str]:
    """Write snapshot/history/audit as UTF-8 (LF) into an explicit directory."""
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    files = {
        "snapshot": target / f"{PART_NAME}_snapshot.json",
        "history": target / f"{PART_NAME}_history.csv",
        "audit": target / f"{PART_NAME}_source_audit.json",
    }
    files["snapshot"].write_bytes((json.dumps(result.part, ensure_ascii=False, indent=1, allow_nan=False) + "\n").encode("utf-8"))
    result.history.to_csv(files["history"], index=False, encoding="utf-8", lineterminator="\n")
    files["audit"].write_bytes((json.dumps({"audit": result.audit, "problems": result.problems},
                                           ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    return {name: str(path) for name, path in files.items()}
