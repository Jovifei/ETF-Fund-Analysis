"""Bounded, provider-free workspace reads. Never fetch the network in a GET.

The old bootstrap hydrates histories and performs several queries per ETF. This
read model instead uses one persisted board plus batched latest-row projections.
Private holdings are joined per request and never enter a shared response cache.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import DailyBar, ForecastSnapshot, Holding, IndicatorSnapshot, Instrument, MarketBar, QuoteSnapshot, ReportArtifact, SectorSnapshot, UserWatchlistEntry
from app.services.decision_board_service import DecisionBoardService
from app.services.factor_analysis_service import DEFAULT_FACTORS
from app.services.support_resistance_service import SupportResistanceService
from app.utils.hashing import stable_hash
from app.workspace.chart import CORE_FIELDS, cached_indicator_series, number
from app.workspace.config import workspace_settings

SHANGHAI = ZoneInfo("Asia/Shanghai")


def iso(value):
    return value.isoformat() if value is not None else None


def market_time(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=SHANGHAI)


def latest_rows(db: Session, model, ids: list[int], *ordering, partitions=None) -> dict:
    if not ids:
        return {}
    partition = partitions or [model.instrument_id]
    ranked = select(model.id, func.row_number().over(partition_by=partition, order_by=[*ordering, model.id.desc()]).label("rn")).where(model.instrument_id.in_(ids)).subquery()
    rows = db.scalars(select(model).join(ranked, model.id == ranked.c.id).where(ranked.c.rn == 1)).all()
    if partitions:
        return {(row.instrument_id, row.horizon): row for row in rows}
    return {row.instrument_id: row for row in rows}


def quote_view(quote, settings: Settings) -> dict:
    if quote is None:
        return {"price": None, "status": "missing", "source_time": None, "source": None, "actionable": False}
    mock = settings.market_provider == "mock" or "mock" in str(quote.source).lower()
    observed = market_time(quote.quote_time)
    age = (datetime.now(UTC) - observed).total_seconds() if observed else None
    state = "mock" if mock else "unverified" if not quote.timestamp_verified else "degraded" if quote.degraded_reason else "stale" if age is None or age < -60 or age > 600 else "observed"
    price = number(quote.price)
    if isinstance(quote.price, bool) or price is None or price <= 0:
        price, state = None, "invalid"
    return {
        "price": price, "change_ratio": number(quote.pct_change / 100) if quote.pct_change is not None else None,
        "status": state, "source_time": iso(observed), "fetched_at": iso(quote.fetched_at),
        "source": quote.source, "timestamp_verified": bool(quote.timestamp_verified),
        "is_realtime": bool(quote.is_realtime and state == "observed"), "is_mock": mock,
        "actionable": False,
    }


def search_instruments(db: Session, settings: Settings, q: str, limit: int, user_id: int | None) -> dict:
    q = q.strip()
    query = select(Instrument).where(Instrument.kind.in_(("ETF", "LOF")))
    if q:
        query = query.where(or_(Instrument.ts_code.contains(q.upper(), autoescape=True), Instrument.name.contains(q, autoescape=True), Instrument.theme_l1.contains(q, autoescape=True), Instrument.theme_l2.contains(q, autoescape=True)))
    query = query.order_by(case((Instrument.ts_code == q.upper(), 0), (Instrument.symbol == q, 1), else_=2), Instrument.ts_code).limit(limit)
    instruments = list(db.scalars(query))
    ids = [row.id for row in instruments]
    quotes = latest_rows(db, QuoteSnapshot, ids, QuoteSnapshot.quote_time.desc())
    watched = set(db.scalars(select(UserWatchlistEntry.instrument_id).where(UserWatchlistEntry.user_id == user_id, UserWatchlistEntry.instrument_id.in_(ids)))) if ids else set()
    held = set(db.scalars(select(Holding.instrument_id).where(Holding.user_id == user_id, Holding.instrument_id.in_(ids)))) if ids else set()
    return {
        "scope": "synced_catalog", "provider_called": False,
        "items": [{"ts_code": row.ts_code, "name": row.name, "kind": row.kind, "theme": row.theme_l1, "theme_detail": row.theme_l2, "enabled": row.enabled, "quote": quote_view(quotes.get(row.id), settings), "watched": row.id in watched, "held": row.id in held} for row in instruments],
        "note": "仅搜索已同步证券目录。新增目录/历史数据由独立任务处理，不阻塞搜索。",
    }


def compact_row(row: dict) -> dict:
    keys = ("ts_code", "name", "kind", "theme_l1", "theme_l2", "grade", "grade_reason", "freshness", "data_status", "return_1d", "return_5d", "returns", "volume", "ma", "macd", "kdj", "rsi", "td", "indicator", "quote", "forecasts", "research_only")
    result = {key: row.get(key) for key in keys}
    history = row.get("history") or []
    result["price"] = number(history[-1].get("close")) if history else number((row.get("support_resistance") or {}).get("current_price"))
    result["price_basis"] = "decision_snapshot"
    result["actionable"] = False
    return result


def overview(db: Session, settings: Settings, horizon: int = 1, offset: int = 0, limit: int = 100, theme: str | None = None) -> dict:
    payload = DecisionBoardService(settings).read_latest(db, horizon=horizon) or {}
    rows = payload.get("rows") or []
    if theme:
        rows = [row for row in rows if theme in (row.get("theme_l1"), row.get("theme_l2"))]
    return {
        "snapshot_id": payload.get("snapshot_id"), "generated_at": payload.get("generated_at"),
        "next_refresh_at": payload.get("next_refresh_at"), "counts": payload.get("counts", {}),
        "freshness_at_capture": payload.get("freshness", "missing"), "horizons": [1, 3, 5, 10],
        "rows": [compact_row(row) for row in rows[offset:offset + limit]],
        "total": len(rows), "offset": offset, "limit": limit,
        "themes": sorted({str(row.get("theme_l1")) for row in payload.get("rows", []) if row.get("theme_l1")}),
        "scope": "tracked_etf_universe_not_all_astocks", "actionable": False, "provider_called": False,
        "contains_mock": settings.market_provider == "mock" or any("mock" in str(row.get("data_status", "")).lower() or "mock" in str((row.get("quote") or {}).get("source", "")).lower() for row in rows),
    }


def holdings_view(db: Session, settings: Settings, user_id: int | None) -> dict:
    pairs = db.execute(select(Holding, Instrument).join(Instrument, Holding.instrument_id == Instrument.id).where(Holding.user_id == user_id).order_by(Holding.id).limit(500)).all()
    quotes = latest_rows(db, QuoteSnapshot, [inst.id for _, inst in pairs], QuoteSnapshot.quote_time.desc())
    board = DecisionBoardService(settings).read_latest(db) or {}
    decisions = {row["ts_code"]: row for row in board.get("rows", [])}
    items = []
    for holding, inst in pairs:
        quote = quote_view(quotes.get(inst.id), settings)
        price = quote["price"]
        shares, cost = float(holding.shares), float(holding.cost_price)
        market_value = shares * price if price is not None else None
        decision = decisions.get(inst.ts_code) or {}
        items.append({
            "ts_code": inst.ts_code, "name": inst.name, "kind": inst.kind, "theme": inst.theme_l1,
            "shares": shares, "cost_price": cost, "quote": quote,
            "market_value": round(market_value, 2) if market_value is not None else None,
            "pnl": round(market_value - shares * cost, 2) if market_value is not None else None,
            "pnl_ratio": price / cost - 1 if price is not None and cost > 0 else None,
            "target_weight": holding.target_weight, "notes": holding.notes, "updated_at": iso(holding.updated_at),
            "grade": decision.get("grade", "数据异常"), "decision_snapshot_id": board.get("snapshot_id"),
            "forecasts": decision.get("forecasts", {}), "support_resistance": decision.get("support_resistance"),
            "actionable": False,
        })
    complete = all(item["market_value"] is not None for item in items)
    subtotal = sum(item["market_value"] or 0 for item in items)
    for item in items:
        item["weight"] = item["market_value"] / subtotal if complete and subtotal > 0 else None
    return {
        "items": items, "priced_subtotal": subtotal, "total_market_value": subtotal if complete else None,
        "pricing_complete": complete, "unpriced_count": sum(item["market_value"] is None for item in items),
        "weight_basis": "recorded_holdings_only_excludes_unrecorded_cash",
        "data_warning": "金额按最后可用报价估算；缺失报价不使用成本冒充现价。",
    }


def instrument_detail(db: Session, settings: Settings, code: str, user_id: int | None) -> dict | None:
    inst = db.scalar(select(Instrument).where(Instrument.ts_code == code, Instrument.kind.in_(("ETF", "LOF"))))
    if inst is None:
        return None
    row = DecisionBoardService(settings).read_instrument(db, code)
    indicator = db.scalar(select(IndicatorSnapshot).where(IndicatorSnapshot.instrument_id == inst.id).order_by(IndicatorSnapshot.as_of_date.desc(), IndicatorSnapshot.generated_at.desc(), IndicatorSnapshot.id.desc()).limit(1))
    quote = latest_rows(db, QuoteSnapshot, [inst.id], QuoteSnapshot.quote_time.desc()).get(inst.id)
    forecasts = latest_rows(db, ForecastSnapshot, [inst.id], ForecastSnapshot.as_of_date.desc(), ForecastSnapshot.generated_at.desc(), partitions=[ForecastSnapshot.instrument_id, ForecastSnapshot.horizon])
    forecast_rows = {}
    for horizon in (1, 3, 5, 10):
        item = forecasts.get((inst.id, horizon))
        if item:
            forecast_rows[str(horizon)] = {name: getattr(item, name) for name in ("p_up", "expected_return", "q10", "q50", "q90", "sample_count", "confidence", "calibration_status", "model_version", "config_hash", "terminal_price_q10", "terminal_price_q50", "terminal_price_q90")}
            forecast_rows[str(horizon)]["as_of_date"] = iso(item.as_of_date)
    personal = next((item for item in holdings_view(db, settings, user_id)["items"] if item["ts_code"] == code), None)
    return {
        "instrument": {"ts_code": code, "name": inst.name, "kind": inst.kind, "theme_l1": inst.theme_l1, "theme_l2": inst.theme_l2, "benchmark": inst.benchmark},
        "decision": compact_row(row) if row else None, "snapshot_id": (row or {}).get("snapshot_id"),
        "decision_time": (row or {}).get("generated_at"), "quote": quote_view(quote, settings),
        "indicator_values": indicator.values_json if indicator else {}, "indicator_version": indicator.version if indicator else None,
        "indicator_as_of": iso(indicator.as_of_date) if indicator else None, "forecasts": forecast_rows,
        "support_resistance": SupportResistanceService(settings).latest(db, inst.id),
        "forecast_scenario": (row or {}).get("forecast_scenario"), "holding": personal,
        "actionable": False, "research_only": True,
    }


def chart_data(db: Session, settings: Settings, code: str, interval: str, limit: int) -> dict | None:
    inst = db.scalar(select(Instrument).where(Instrument.ts_code == code, Instrument.kind.in_(("ETF", "LOF"))))
    if inst is None:
        return None
    if interval != "1d":
        rows = list(reversed(db.scalars(select(MarketBar).where(MarketBar.instrument_id == inst.id, MarketBar.interval == interval).order_by(MarketBar.bar_time.desc()).limit(limit)).all()))
        return {"ts_code": code, "interval": interval, "available": bool(rows), "bars": [{"date": iso(market_time(row.bar_time)), "open": row.open, "high": row.high, "low": row.low, "close": row.close, "volume": row.volume, "amount": row.amount, "source": row.source, "indicators": {}} for row in rows], "reason": None if rows else "minute_data_unavailable", "qualification": "unverified", "cost_overlay_allowed": False, "sr_overlay_allowed": False, "actionable": False, "indicator_note": "分钟指标尚未取得统一口径资格，不用日线指标代替。"}
    adjustments = list(db.scalars(select(DailyBar.adjust).where(DailyBar.instrument_id == inst.id).distinct()))
    adjust = "none" if "none" in adjustments else adjustments[0] if len(adjustments) == 1 else None
    if adjust is None:
        return {"ts_code": code, "interval": interval, "available": False, "bars": [], "reason": "missing_or_ambiguous_price_basis", "actionable": False}
    maximum = workspace_settings().chart_history_limit
    stored = db.scalars(select(DailyBar).where(DailyBar.instrument_id == inst.id, DailyBar.adjust == adjust).order_by(DailyBar.trade_date.desc()).limit(maximum + 1)).all()
    truncated = len(stored) > maximum
    stored = list(reversed(stored[:maximum]))
    rows = [{"date": iso(row.trade_date), "open": row.open, "high": row.high, "low": row.low, "close": row.close, "volume": row.volume, "amount": row.amount, "source": row.source} for row in stored]
    if any(any(number(row[key]) is None for key in ("open", "high", "low", "close")) or row["low"] > min(row["open"], row["close"]) or row["high"] < max(row["open"], row["close"]) for row in rows):
        return {"ts_code": code, "interval": interval, "available": False, "bars": [], "reason": "invalid_ohlc", "actionable": False}
    strategy = settings.load_strategy()
    series = cached_indicator_series(rows, strategy["indicator"])
    now = datetime.now(SHANGHAI)
    for row in series:
        row["is_partial"] = row["date"] == now.date().isoformat() and now.time() < time(15, 0)
    snapshot = db.scalar(select(IndicatorSnapshot).where(IndicatorSnapshot.instrument_id == inst.id).order_by(IndicatorSnapshot.as_of_date.desc(), IndicatorSnapshot.generated_at.desc(), IndicatorSnapshot.id.desc()).limit(1))
    matches = None
    if snapshot and series and iso(snapshot.as_of_date) == series[-1]["date"]:
        values = snapshot.values_json or {}
        comparable = [key for key in CORE_FIELDS if number(values.get(key)) is not None and series[-1]["indicators"].get(key) is not None]
        matches = all(abs(float(values[key]) - series[-1]["indicators"][key]) <= (0.011 if key.startswith(("kdj", "rsi")) else 0.00011) for key in comparable) if comparable else None
    mock = settings.market_provider == "mock" or any("mock" in str(row["source"]).lower() for row in rows)
    sr = SupportResistanceService(settings).latest(db, inst.id)
    return {
        "ts_code": code, "interval": interval, "available": bool(series), "bars": series[-limit:],
        "adjust": adjust, "currency": "CNY", "source_bars": len(rows), "history_truncated": truncated,
        "indicator_version": strategy["indicator_version"], "indicator_basis": "shared_python_core_formulas_full_available_history",
        "core_snapshot_match": matches, "source_as_of": rows[-1]["date"] if rows else None,
        "qualification": "mock" if mock else "research_only", "actionable": False,
        "cost_overlay_allowed": adjust == "none", "sr_overlay_allowed": len(adjustments) == 1 and bool(sr),
        "support_resistance": sr if len(adjustments) == 1 else None,
        "indicator_note": "图表由服务端统一公式生成；支撑压力为当前快照，不是历史当时已知的点位。",
    }


def factor_view(db: Session, settings: Settings) -> dict:
    configured = list(settings.load_strategy().get("factor_analysis", {}).get("factors", DEFAULT_FACTORS))
    artifact = db.scalar(select(ReportArtifact).where(ReportArtifact.report_type == "factor_effectiveness", ReportArtifact.user_id.is_(None)).order_by(ReportArtifact.as_of_time.desc(), ReportArtifact.id.desc()).limit(1))
    report = None
    if artifact:
        try:
            path = Path(artifact.file_path).resolve(strict=True)
            path.relative_to(settings.reports_dir.resolve())
            with path.open("rb") as handle:
                raw = handle.read(4_000_001)
            if len(raw) > 4_000_000:
                raise ValueError("report too large")
            parsed = json.loads(raw)
            if parsed.get("report_type") == "factor_effectiveness" and stable_hash(parsed) == artifact.content_hash:
                report = parsed
        except (OSError, ValueError, TypeError):
            report = None
    return {"registry": [{"name": name, "status": "research_candidate", "strategy_promotion": False} for name in configured], "name_count": len(configured), "validated_count": None, "report": report, "actionable": False, "note": "名称数量不是独立有效因子数量；诊断结果不代表样本外合格。"}


def portfolio_risk(db: Session, settings: Settings, user_id: int | None) -> dict:
    portfolio = holdings_view(db, settings, user_id)
    items = portfolio["items"][:60]
    codes = [item["ts_code"] for item in items]
    pairs = db.execute(select(Instrument.ts_code, DailyBar).join(DailyBar, DailyBar.instrument_id == Instrument.id).where(Instrument.ts_code.in_(codes), DailyBar.adjust == "none").order_by(DailyBar.trade_date.desc()).limit(20000)).all() if codes else []
    records = [{"code": code, "date": bar.trade_date, "close": bar.close} for code, bar in pairs]
    correlations = []
    if records:
        prices = pd.DataFrame(records).pivot(index="date", columns="code", values="close").sort_index().tail(121)
        returns = prices.pct_change(fill_method=None)
        for i, left in enumerate(codes):
            for right in codes[i + 1:]:
                if left not in returns or right not in returns:
                    continue
                sample = returns[[left, right]].dropna()
                correlation = sample[left].corr(sample[right]) if len(sample) >= 40 else None
                correlations.append({"left": left, "right": right, "correlation": number(correlation), "observations": len(sample)})
    theme_weights: dict[str, float] = {}
    for item in items:
        if item["weight"] is not None:
            key = item["theme"] or "未分类"
            theme_weights[key] = theme_weights.get(key, 0) + item["weight"]
    return {"pricing_complete": portfolio["pricing_complete"], "max_weight": max((item["weight"] or 0 for item in items), default=0) if portfolio["pricing_complete"] else None, "theme_weights": theme_weights, "correlations": correlations, "basis": "last_120_daily_return_pearson_unadjusted_research", "limitations": ["不含未录入现金和资产", "收益相关性不是成分股重叠", "未复权收益会受分红影响", "个人成本不参与共享市场信号"], "actionable": False}


def sector_overview(db: Session, settings: Settings) -> dict:
    """Two bounded read-only SQL queries; no all-market grade/indicator hydration."""
    ranked = select(SectorSnapshot.id, func.row_number().over(partition_by=[SectorSnapshot.board_type, SectorSnapshot.sector_name], order_by=[SectorSnapshot.trade_date.desc(), SectorSnapshot.fetched_at.desc(), SectorSnapshot.id.desc()]).label("rn")).subquery()
    rows = db.scalars(select(SectorSnapshot).join(ranked, ranked.c.id == SectorSnapshot.id).where(ranked.c.rn == 1).order_by(SectorSnapshot.board_type, SectorSnapshot.sector_name).limit(1000)).all()
    boards = []
    for row in rows:
        total = row.total_count or 0
        valid_breadth = total > 0 and sum((row.up_count or 0, row.down_count or 0, row.flat_count or 0)) == total
        boards.append({"board_type": row.board_type, "sector_name": row.sector_name, "sector_pct_change": number(row.pct_change), "source": row.source, "source_as_of": iso(row.trade_date), "fetched_at": iso(row.fetched_at), "is_mock": settings.market_provider == "mock" or "mock" in row.source.lower(), "breadth": {"trade_date": iso(row.trade_date), "available": valid_breadth, "up": row.up_count if valid_breadth else None, "down": row.down_count if valid_breadth else None, "flat": row.flat_count if valid_breadth else None, "total": total if valid_breadth else None}})
    return {"boards": boards, "scope": "persisted_sector_snapshots", "pct_change_unit": "percentage_points", "source_as_of": max((iso(row.trade_date) for row in rows), default=None), "freshness": "read_source_dates_not_live" if rows else "missing", "actionable": False}
