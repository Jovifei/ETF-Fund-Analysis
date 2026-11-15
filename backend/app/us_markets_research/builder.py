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
    frames = {}
    quality_audit = []
    excluded_provisional = []
    for ticker, frame in fetched.frames.items():
        frame = frame.copy()
        if as_of:
            frame = frame[frame.index <= pd.Timestamp(as_of)]
        provisional = frame["close_source"].astype(str).str.contains("provisional", case=False)
        for day in frame.index[provisional]:
            excluded_provisional.append({"ticker": ticker, "date": str(day.date()), "excluded_from_metrics": True})
        regular_start = config.get("regular_trading_start", {}).get(ticker)
        before_regular = frame.index < pd.Timestamp(regular_start) if regular_start else pd.Series(False, index=frame.index)
        quality_audit.append({"ticker": ticker, "input_rows": len(frame),
                              "excluded_provisional_rows": int(provisional.sum()),
                              "excluded_pre_regular_rows": int(sum(before_regular)),
                              "regular_trading_start": regular_start,
                              "observed_first": str(frame.index[0].date()) if len(frame) else None,
                              "observed_last": str(frame.index[-1].date()) if len(frame) else None})
        # Keep excluded dates as NaN so missing internal sessions cannot disappear.
        price_cols = ["open", "high", "low", "close", "volume"]
        frame.loc[provisional, price_cols] = float("nan")
        frame = frame.loc[~before_regular]
        if frame["close"].notna().any():
            frames[ticker] = frame
    # Observed union-session calendar (not an exchange-certified calendar).
    # Restore missing dates within each name's listed interval before computing.
    if frames:
        calendar = pd.DatetimeIndex(sorted(set().union(*(set(f.index) for f in frames.values()))))
        for ticker, frame in list(frames.items()):
            first = frame["close"].first_valid_index()
            if first is not None:
                frames[ticker] = frame.reindex(calendar[calendar >= first])
                audit = next(q for q in quality_audit if q["ticker"] == ticker)
                audit["missing_observed_calendar_sessions"] = int(frames[ticker]["close"].isna().sum())
                audit["confirmed_first"] = str(first.date())
                audit["confirmed_last"] = str(frame["close"].last_valid_index().date())
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
                 "coverage_note": _coverage_note(meta, members), "first_gap_date": meta.get("first_gap_date"),
                 "membership_policy": config.get("membership_policy"),
                 "membership_warning": config.get("membership_warning"),
                 "synthetic_ohlc_warning": "等权成分日高低的组合包络，不是同时可成交篮子高低；ATR/道氏仅合成代理。"}
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
        df = frame.assign(provisional=False)
        # Refuse compression over missing internal sessions for ATR and returns.
        first = df["close"].first_valid_index()
        df = df.loc[first:]
        missing = df["close"].isna()
        if missing.any():
            df = df.loc[df.index < df.index[missing][0]]
        if df.empty:
            series.append(_unavailable(item, kind="index", reason="no_confirmed_close", meta={}))
            continue
        extra = {"official_index": True, "market_context_id": item.get("market_context_id"),
                 "coverage_note": "官方指数；此处为研究对照序列，首页指数卡片读数以原有新浪通道为准。"}
        series.append(series_entry(series_id=item["series_id"], label=item["label"], group_id=item["group_id"],
                                   kind="index", df=df, with_volume=True, benchmarks=bench_for(item["series_id"]),
                                   source_label=source_label, extra=extra))
        history_parts.append(_history(item["series_id"], df))

    available = [s for s in series if s.get("available")]
    dates = [s["as_of"] for s in available]
    availability = "unavailable" if not available else ("available" if len(available) == len(series) and not excluded_provisional and len(set(dates)) <= 1 and not any(s.get("first_gap_date") for s in available) else "partial")
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
        "provisional_closes": [],
        "excluded_provisional_observations": excluded_provisional,
        "quality_audit": quality_audit,
        "membership_policy": config.get("membership_policy"),
        "listing_sources": config.get("listing_sources", []),
        "membership_warning": config.get("membership_warning"),
        "price_policy": "provider_adjusted_daily_OHLC_only; provisional_excluded; no_factor_fill",
        "corporate_action_validation": "vendor_adjustment_not_independently_reconciled",
        "failed_tickers": sorted({a["ticker"] for a in fetched.audit if not a["ok"] and a.get("ticker")}),
        "groups": config["groups"], "series": series,
    }
    # Explicit cross-series and full-current-constituent common samples.
    available_history = [h for h in history_parts if not h.empty]
    common_levels = sorted(set.intersection(*(set(h["date"]) for h in available_history))) if available_history else []
    required = required_tickers(config)
    common_member_returns = []
    if all(t in frames for t in required):
        date_sets = [set(frames[t].index[frames[t]["close"].notna() & frames[t]["close"].shift(1).notna()]) for t in required]
        common_member_returns = sorted(set.intersection(*date_sets))
    def span(days):
        return {"first": str(days[0].date()) if days else None,
                "last": str(days[-1].date()) if days else None, "n_sessions": len(days)}
    part["common_samples"] = {
        "available_series_level_overlap": span(common_levels),
        "all_current_members_adjacent_return_overlap": span(common_member_returns),
        "note": "后一窗口要求全部当前成分与指数有同日和前一观察交易日的有效价格；不是 PIT 成分验证。"}
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
        values = frame["close"]
        first_valid = values.first_valid_index()
        values = values.loc[first_valid:] if first_valid is not None else values.iloc[:0]
        gaps = values[values.isna()]
        close = values.loc[values.index < gaps.index[0]] if not gaps.empty else values
        if close.empty:
            rows.append({"ticker": ticker, "name": ticker, "available": False})
            continue
        rows.append({
            "ticker": ticker, "name": config["member_names"].get(ticker, ticker), "available": True,
            "first_date": str(close.index[0].date()), "as_of": str(close.index[-1].date()),
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
    files["audit"].write_bytes((json.dumps({"audit": result.audit, "problems": result.problems,
                                           "quality_audit": result.part.get("quality_audit", []),
                                           "excluded_provisional_observations": result.part.get("excluded_provisional_observations", []),
                                           "listing_sources": result.part.get("listing_sources", [])},
                                           ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    return {name: str(path) for name, path in files.items()}
