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
from app.models import (
    DailyBar,
    DecisionBoardProvisionalInput,
    DecisionBoardSnapshot,
    ForecastSnapshot,
    Holding,
    IndicatorSnapshot,
    Instrument,
    MarketBar,
    QuoteSnapshot,
    ReportArtifact,
    SectorSnapshot,
    UserWatchlistEntry,
)
from app.services.decision_board_service import DecisionBoardService
from app.services.factor_analysis_service import DEFAULT_FACTORS
from app.services.support_resistance_service import SupportResistanceService
from app.utils.hashing import stable_hash
from app.workspace.catalog_search import matching_reason, search_terms
from app.workspace.chart import CORE_FIELDS, cached_indicator_series, number
from app.workspace.config import workspace_settings

SHANGHAI = ZoneInfo("Asia/Shanghai")

_SEARCH_ALIASES = {
    # Cross-border products are not consistently labeled with the word
    # "跨境"; keep the category search bounded to the synchronized catalog.
    "跨境": ("跨境", "港股", "恒生", "纳斯达克", "标普", "海外", "美国", "原油"),
}


def iso(value):
    return value.isoformat() if value is not None else None


def market_time(value):
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
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


def quote_view(quote, settings: Settings, *, as_of: datetime | None = None) -> dict:
    if quote is None:
        return {"price": None, "status": "missing", "source_time": None, "source": None, "actionable": False}
    mock = settings.market_provider == "mock" or "mock" in str(quote.source).lower()
    observed = market_time(quote.quote_time)
    reference = market_time(as_of or datetime.now(UTC))
    age = (reference.astimezone(UTC) - observed.astimezone(UTC)).total_seconds() if observed else None
    state = "mock" if mock else "unverified" if not quote.timestamp_verified else "degraded" if quote.degraded_reason else "stale" if age is None or age < 0 or age > 600 else "observed"
    price = number(quote.price)
    if isinstance(quote.price, bool) or price is None or price <= 0:
        price, state = None, "invalid"
    source_time_missing = str(quote.degraded_reason or "").startswith("source_timestamp_missing")
    return {
        "price": price, "change_ratio": number(quote.pct_change / 100) if quote.pct_change is not None else None,
        "status": state, "source_time": None if source_time_missing else iso(observed), "fetched_at": iso(quote.fetched_at),
        "source": quote.source, "timestamp_verified": bool(quote.timestamp_verified),
        "is_realtime": bool(quote.is_realtime and state == "observed"), "is_mock": mock,
        "actionable": False,
    }


def _decision_delta(db: Session, current: dict | None) -> dict:
    if not current or not current.get("snapshot_id"):
        return {"status": "unavailable", "reason_code": "decision_not_generated"}
    snapshots = list(db.scalars(select(DecisionBoardSnapshot).order_by(
        DecisionBoardSnapshot.generated_at.desc(), DecisionBoardSnapshot.id.desc()
    ).limit(20)))
    current_index = next((i for i, item in enumerate(snapshots) if item.snapshot_id == current["snapshot_id"]), None)
    if current_index is None or current_index + 1 >= len(snapshots):
        return {"status": "unavailable", "reason_code": "no_previous_snapshot"}
    previous = snapshots[current_index + 1]
    previous_row = next((item for item in (previous.payload_json or {}).get("rows", [])
                         if item.get("ts_code") == current.get("ts_code")), None)
    if previous_row is None:
        return {"status": "unavailable", "reason_code": "instrument_absent_from_previous_snapshot",
                "previous_snapshot_id": previous.snapshot_id}
    return {
        "status": "available", "previous_snapshot_id": previous.snapshot_id,
        "previous_grade": previous_row.get("grade"), "current_grade": current.get("grade"),
        "grade_changed": previous_row.get("grade") != current.get("grade"),
        "previous_data_status": previous_row.get("data_status"), "current_data_status": current.get("data_status"),
        "data_status_changed": previous_row.get("data_status") != current.get("data_status"),
    }


def search_instruments(db: Session, settings: Settings, q: str, limit: int, user_id: int | None, *, offset: int = 0, sort: str = "relevance", min_scale: float = 0, include_unknown: bool = True) -> dict:
    q = q.strip()
    query = select(Instrument).where(Instrument.kind.in_(("ETF", "LOF")))
    terms, match_context = search_terms(q)
    if q:
        query = query.where(or_(*[condition for term in terms for condition in (
            Instrument.ts_code.contains(term.upper(), autoescape=True),
            Instrument.name.contains(term, autoescape=True),
            Instrument.theme_l1.contains(term, autoescape=True),
            Instrument.theme_l2.contains(term, autoescape=True),
            Instrument.benchmark.contains(term, autoescape=True),
            Instrument.metadata_json["index_name"].as_string().contains(term, autoescape=True),
        )]))
    scale = Instrument.metadata_json["market_cap_cny"].as_float()
    turnover = Instrument.metadata_json["turnover_cny"].as_float()
    if min_scale > 0:
        query = query.where(or_(scale >= min_scale, scale.is_(None)) if include_unknown else scale >= min_scale)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    priority = [case((Instrument.ts_code == q.upper(), 0), (Instrument.symbol == q, 1), else_=2)]
    if sort == "scale":
        priority += [scale.desc().nulls_last()]
    elif sort == "turnover":
        priority += [turnover.desc().nulls_last()]
    query = query.order_by(*priority, Instrument.ts_code).offset(offset).limit(limit)
    instruments = list(db.scalars(query))
    ids = [row.id for row in instruments]
    quotes = latest_rows(db, QuoteSnapshot, ids, QuoteSnapshot.quote_time.desc())
    watched = set(db.scalars(select(UserWatchlistEntry.instrument_id).where(UserWatchlistEntry.user_id == user_id, UserWatchlistEntry.instrument_id.in_(ids)))) if ids else set()
    held = set(db.scalars(select(Holding.instrument_id).where(Holding.user_id == user_id, Holding.instrument_id.in_(ids)))) if ids else set()
    return {
        "scope": "synced_catalog", "match_context": match_context, "provider_called": False, "total": total, "offset": offset, "limit": limit, "has_more": offset + len(instruments) < total,
        "items": [{"ts_code": row.ts_code, "name": row.name, "kind": row.kind, "theme": row.theme_l1, "theme_detail": row.theme_l2, "enabled": row.enabled, "quote": quote_view(quotes.get(row.id), settings), "match_reason": matching_reason(row, terms), "market_cap_cny": (row.metadata_json or {}).get("market_cap_cny"), "turnover_cny": (row.metadata_json or {}).get("turnover_cny"), "metadata_as_of": (row.metadata_json or {}).get("catalog_as_of"), "watched": row.id in watched, "held": row.id in held} for row in instruments],
        "note": "仅搜索已同步证券目录。新增目录/历史数据由独立任务处理，不阻塞搜索。",
    }


def compact_row(row: dict) -> dict:
    keys = ("ts_code", "name", "kind", "theme_l1", "theme_l2", "grade", "grade_reason", "freshness", "data_status", "return_1d", "return_5d", "returns", "volume", "ma", "macd", "kdj", "rsi", "td", "sector", "chan", "indicator", "indicator_as_of", "provisional", "quote", "forecasts", "research_only", "entry_exit_ref", "theme_relative_strength", "support_resistance")
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


def instrument_detail(db: Session, settings: Settings, code: str, user_id: int | None, *, as_of: datetime | None = None) -> dict | None:
    read_as_of = market_time(as_of or datetime.now(SHANGHAI)).astimezone(SHANGHAI)
    inst = db.scalar(select(Instrument).where(Instrument.ts_code == code, Instrument.kind.in_(("ETF", "LOF"))))
    if inst is None:
        return None
    row = DecisionBoardService(settings).read_instrument(db, code)
    decision_after_read = bool(row and market_time(row.get("generated_at")) > read_as_of)
    if decision_after_read:
        row = None
    indicator = db.scalar(select(IndicatorSnapshot).where(IndicatorSnapshot.instrument_id == inst.id).order_by(IndicatorSnapshot.as_of_date.desc(), IndicatorSnapshot.generated_at.desc(), IndicatorSnapshot.id.desc()).limit(1))
    quote = latest_rows(db, QuoteSnapshot, [inst.id], QuoteSnapshot.quote_time.desc()).get(inst.id)
    forecasts = latest_rows(db, ForecastSnapshot, [inst.id], ForecastSnapshot.as_of_date.desc(), ForecastSnapshot.generated_at.desc(), partitions=[ForecastSnapshot.instrument_id, ForecastSnapshot.horizon])
    from app.services.settlement import settled_session
    from app.services.snapshot_contract import snapshot_issues
    expected = None if settings.market_provider == "mock" else settled_session(settings, read_as_of)
    indicator_issues = snapshot_issues(indicator, settings, expected, kind="indicator")
    if indicator is not None and market_time(indicator.generated_at) > read_as_of:
        indicator_issues = [*indicator_issues, "indicator_snapshot_after_read_time"]
    forecast_issues = {str(h): snapshot_issues(forecasts.get((inst.id, h)), settings, expected, kind="forecast")
                       for h in (1, 3, 5, 10)}
    for horizon in (1, 3, 5, 10):
        forecast = forecasts.get((inst.id, horizon))
        if forecast is not None and market_time(forecast.generated_at) > read_as_of:
            forecast_issues[str(horizon)] = [*forecast_issues[str(horizon)], "forecast_snapshot_after_read_time"]
    if indicator_issues:
        indicator = None
    forecast_rows = {}
    for horizon in (1, 3, 5, 10):
        item = forecasts.get((inst.id, horizon))
        if item and not forecast_issues[str(horizon)]:
            forecast_rows[str(horizon)] = {name: getattr(item, name) for name in ("p_up", "expected_return", "q10", "q50", "q90", "sample_count", "confidence", "calibration_status", "model_version", "config_hash", "terminal_price_q10", "terminal_price_q50", "terminal_price_q90")}
            forecast_rows[str(horizon)]["as_of_date"] = iso(item.as_of_date)
    from app.providers.data_contract import history_issues
    issue = history_issues(db, settings, [inst.id]).get(inst.id)
    view_quote = quote_view(quote, settings, as_of=read_as_of)
    display_chart = chart_data(db, settings, code, "1d", 60, as_of=read_as_of)
    raw_chart_bars = (display_chart or {}).get("bars") or []
    research_chart_bars = (display_chart or {}).get("research_bars") or raw_chart_bars
    last = (raw_chart_bars or [None])[-1]
    research_last = (research_chart_bars or [None])[-1]
    display_values = (research_last or {}).get("indicators") or (indicator.values_json if indicator and not issue else {})
    indicator_as_of = research_last["date"] if research_last and display_values else iso(indicator.as_of_date) if indicator and not issue else None
    if view_quote["price"] is None and last:
        view_quote = {**view_quote, "price": last["close"], "status": "historical_close",
                      "source": last["source"], "source_time": last["date"],
                      "price_basis": "historical_close", "is_realtime": False}
    if issue:
        forecast_rows = {}
    personal = next((item for item in holdings_view(db, settings, user_id)["items"] if item["ts_code"] == code), None)
    indicator_available = any(number(value) is not None for value in display_values.values())
    history_reason = (display_chart or {}).get("reason") if not (display_chart or {}).get("available") else None
    volume_missing = (display_chart or {}).get("qualification") in {"legacy_units_unverified", "historical_price_only"} or any(
        bar.get("volume") is None for bar in (display_chart or {}).get("bars", [])
    )
    chart_available = bool((display_chart or {}).get("available"))
    chart_history_issue = (display_chart or {}).get("history_issue")
    decision_reason = "decision_snapshot_after_read_time" if decision_after_read else None if row else "decision_not_generated"
    forecast_reason = (
        None if forecast_rows else "forecast_snapshot_after_read_time"
        if any("forecast_snapshot_after_read_time" in reasons for reasons in forecast_issues.values())
        else issue or "forecast_not_generated"
    )
    availability = {
        "instrument": {"status": "active" if inst.enabled else "disabled", "reason_code": None if inst.enabled else "instrument_disabled"},
        "price": {"status": "available" if view_quote["price"] is not None else "unavailable", "reason_code": None if view_quote["price"] is not None else "quote_unavailable"},
        "history": {"status": "blocked" if chart_history_issue else "available" if chart_available else "unavailable",
                    "reason_code": chart_history_issue or (None if chart_available else history_reason or "history_not_prepared")},
        "price_basis": {"status": "unknown" if not chart_available else "aligned" if (display_chart or {}).get("raw_overlay_allowed", True) else "separate",
                         "reason_code": chart_history_issue or (display_chart or {}).get("raw_overlay_reason") or (None if chart_available else history_reason)},
        "indicators": {"status": "blocked" if chart_history_issue else "available" if indicator_available else "unavailable",
                        "reason_code": chart_history_issue or (None if indicator_available else "indicator_values_unavailable")},
        "volume": {"status": "blocked" if chart_history_issue else "unavailable" if volume_missing else "available",
                   "reason_code": chart_history_issue or ("volume_missing_or_unverified" if volume_missing else None)},
        "forecasts": {"status": "blocked" if issue else "available" if forecast_rows else "unavailable",
                       "reason_code": forecast_reason},
        "decision": {"status": "available" if row else "unavailable",
                     "reason_code": decision_reason},
    }
    decision_explanation = {
        "conclusion": row.get("grade") if row else None,
        "primary_basis": row.get("grade_reason") if row else None,
        "comparison": {"status": "unavailable", "reason_code": decision_reason} if decision_after_read else _decision_delta(db, row),
        "evidence_caveats": [item["reason_code"] for item in availability.values() if item.get("reason_code")],
        "computed_at": row.get("generated_at") if row else None,
        "actionable": False,
    }
    return {
        "instrument": {"ts_code": code, "name": inst.name, "kind": inst.kind, "theme_l1": inst.theme_l1, "theme_l2": inst.theme_l2, "benchmark": inst.benchmark, "enabled": bool(inst.enabled)},
        "decision": compact_row(row) if row else None, "snapshot_id": (row or {}).get("snapshot_id"),
        "decision_time": (row or {}).get("generated_at"), "quote": view_quote,
        "availability": availability, "decision_explanation": decision_explanation,
        "snapshot_issues": {"indicator": indicator_issues, "forecasts": forecast_issues},
        "read_as_of": iso(read_as_of), "daily_as_of": (display_chart or {}).get("source_as_of") or (last or {}).get("date"),
        "target_trade_date": expected.isoformat() if expected else None,
        "history_issue": issue, "indicator_basis": (display_chart or {}).get("indicator_basis") or ("persisted_snapshot" if indicator and not issue else "historical_price_display"),
        "indicator_input_hash": (display_chart or {}).get("input_hash"), "chart_series_id": (display_chart or {}).get("series_id"),
        "indicator_values": display_values, "indicator_version": (display_chart or {}).get("indicator_version") or (indicator.version if indicator and not issue else settings.load_strategy()["indicator_version"]),
        "indicator_as_of": indicator_as_of, "forecasts": forecast_rows,
        "support_resistance": None if issue or not (display_chart or {}).get("raw_overlay_allowed", True) else SupportResistanceService(settings).latest(db, inst.id),
        "forecast_scenario": DecisionBoardService._forecast_scenario(
            (display_chart or {}).get("research_bars", []), forecast_rows), "holding": personal,
        "actionable": False, "research_only": True,
    }


def chart_data(db: Session, settings: Settings, code: str, interval: str, limit: int, *, as_of: datetime | None = None) -> dict | None:
    as_of = market_time(as_of or datetime.now(SHANGHAI)).astimezone(SHANGHAI)
    if interval in ("1w", "1mo"):
        from app.workspace.candle_periods import transform_chart
        raw=chart_data(db,settings,code,"1d",workspace_settings().chart_history_limit,as_of=as_of)
        return transform_chart(raw,interval,settings.load_strategy()["indicator"],limit,now=as_of) if raw else None
    inst = db.scalar(select(Instrument).where(Instrument.ts_code == code, Instrument.kind.in_(("ETF", "LOF"))))
    if inst is None:
        return None
    if interval != "1d":
        rows = list(reversed(db.scalars(select(MarketBar).where(
            MarketBar.instrument_id == inst.id, MarketBar.interval == interval, MarketBar.bar_time <= as_of
        ).order_by(MarketBar.bar_time.desc()).limit(limit)).all()))
        return {"ts_code": code, "interval": interval, "available": bool(rows), "bars": [{"date": iso(market_time(row.bar_time)), "open": row.open, "high": row.high, "low": row.low, "close": row.close, "volume": row.volume, "amount": row.amount, "source": row.source, "indicators": {}} for row in rows], "reason": None if rows else "minute_data_unavailable", "qualification": "unverified", "as_of": iso(as_of), "computed_at": iso(datetime.now(SHANGHAI)), "source_as_of": iso(market_time(rows[-1].bar_time)) if rows else None, "cost_overlay_allowed": False, "sr_overlay_allowed": False, "actionable": False, "indicator_note": "分钟指标尚未取得统一口径资格，不用日线指标代替。"}
    adjustments = list(db.scalars(select(DailyBar.adjust).where(
        DailyBar.instrument_id == inst.id, DailyBar.trade_date <= as_of.date()
    ).distinct()))
    if not adjustments:
        return {"ts_code": code, "interval": interval, "available": False, "bars": [], "reason": "history_not_prepared", "as_of": iso(as_of), "computed_at": iso(datetime.now(SHANGHAI)), "actionable": False}
    adjust = "none" if "none" in adjustments else adjustments[0] if len(adjustments) == 1 else None
    if adjust is None:
        return {"ts_code": code, "interval": interval, "available": False, "bars": [], "reason": "missing_or_ambiguous_price_basis", "as_of": iso(as_of), "computed_at": iso(datetime.now(SHANGHAI)), "actionable": False}
    maximum = workspace_settings().chart_history_limit
    stored = db.scalars(select(DailyBar).where(
        DailyBar.instrument_id == inst.id, DailyBar.adjust == adjust, DailyBar.trade_date <= as_of.date()
    ).order_by(DailyBar.trade_date.desc()).limit(maximum + 1)).all()
    truncated = len(stored) > maximum
    stored = list(reversed(stored[:maximum]))
    from app.providers.corporate_action_contract import research_history_rows
    from app.providers.corporate_action_contract import research_price_basis as build_research_price_basis
    research_stored = (
        stored
        if settings.market_provider == "mock" or adjust != "none"
        else research_history_rows(stored, code, effective_through=as_of.date())
    )
    research_objects = list(research_stored)
    rows = [{"date": iso(row.trade_date), "open": row.open, "high": row.high, "low": row.low, "close": row.close, "volume": row.volume, "amount": row.amount, "source": row.source} for row in stored]
    research_rows = [{"date": iso(row.trade_date), "open": row.open, "high": row.high, "low": row.low, "close": row.close, "volume": row.volume, "amount": row.amount, "source": row.source} for row in research_stored]
    if any(any(number(row[key]) is None for key in ("open", "high", "low", "close")) or row["low"] > min(row["open"], row["close"]) or row["high"] < max(row["open"], row["close"]) for row in rows):
        return {"ts_code": code, "interval": interval, "available": False, "bars": [], "reason": "invalid_ohlc", "as_of": iso(as_of), "computed_at": iso(datetime.now(SHANGHAI)), "actionable": False}
    strategy = settings.load_strategy()
    from app.providers.data_contract import LEGACY_SOURCES, UNVERIFIED_UNIT_SOURCES, price_history_issue
    from app.services.decision_board_service import DecisionBoardService
    provisional = db.scalar(select(DecisionBoardProvisionalInput).where(
        DecisionBoardProvisionalInput.instrument_id == inst.id,
    ).order_by(DecisionBoardProvisionalInput.observed_at.desc(), DecisionBoardProvisionalInput.id.desc()).limit(1))
    provisional_status = DecisionBoardService(settings)._provisional_status(
        db, inst.id, provisional, as_of
    ) if provisional is not None else {"used_for_derived_values": False}
    if provisional_status.get("used_for_derived_values") and provisional is not None:
        from types import SimpleNamespace
        provisional_bar = {
            "date": iso(market_time(provisional.observed_at)), "open": provisional.open_price,
            "high": provisional.high_price, "low": provisional.low_price,
            "close": provisional.last_price, "volume": provisional.volume,
            "amount": provisional.amount, "source": provisional.source,
            "is_provisional": True, "timestamp_verified": bool(provisional.timestamp_verified),
        }
        provisional_object = SimpleNamespace(
            trade_date=market_time(provisional.observed_at).date(), open=provisional.open_price,
            high=provisional.high_price, low=provisional.low_price, close=provisional.last_price,
            pre_close=None, volume=provisional.volume, amount=provisional.amount,
            source=provisional.source, adjust=adjust, fetched_at=provisional.created_at,
            quality_hash=None,
        )
        research_provisional = (
            provisional_object
            if settings.market_provider == "mock" or adjust != "none"
            else research_history_rows(
                [provisional_object], code, effective_through=as_of.date()
            )[0]
        )
        research_provisional_bar = {
            **provisional_bar, "open": research_provisional.open, "high": research_provisional.high,
            "low": research_provisional.low, "close": research_provisional.close,
            "volume": research_provisional.volume, "amount": research_provisional.amount,
        }
        provisional_day = provisional_bar["date"][:10]
        same_day_index = next((i for i, bar in enumerate(rows) if bar["date"][:10] == provisional_day), None)
        if same_day_index is not None and as_of.date().isoformat() == provisional_day and as_of.time() >= time(15, 15):
            provisional_status = {**provisional_status, "status": "settled_daily_preferred", "used_for_derived_values": False, "reason": "settled_daily_bar_preferred"}
        elif same_day_index is None:
            rows.append(provisional_bar)
            research_rows.append(research_provisional_bar)
            research_objects.append(research_provisional)
        else:
            rows[same_day_index] = provisional_bar
            research_rows[same_day_index] = research_provisional_bar
            research_objects[same_day_index] = research_provisional
    if any(any(number(row[key]) is None for key in ("open", "high", "low", "close")) or row["low"] > min(row["open"], row["close"]) or row["high"] < max(row["open"], row["close"]) for row in rows):
        return {"ts_code": code, "interval": interval, "available": False, "bars": [], "reason": "invalid_ohlc", "as_of": iso(as_of), "computed_at": iso(datetime.now(SHANGHAI)), "actionable": False}
    legacy_units = settings.market_provider != "mock" and any(row["source"] in LEGACY_SOURCES + UNVERIFIED_UNIT_SOURCES for row in rows)
    if legacy_units:
        rows = [{**row, "volume": None, "amount": None} for row in rows]
        research_rows = [{**row, "volume": None, "amount": None} for row in research_rows]
    continuity_issue = price_history_issue(research_objects) if research_objects else None
    if continuity_issue:
        research_series = [{**row, "indicators": {}, "history_issue": continuity_issue} for row in research_rows]
    else:
        computed = cached_indicator_series(research_rows, strategy["indicator"])
        research_series = [{**row, "indicators": computed[index].get("indicators", {}), "history_issue": None}
                           for index, row in enumerate(research_rows)]
    price_basis_changed = any(
        number(raw.get(key)) is not None and number(research.get(key)) is not None
        and abs(float(raw[key]) - float(research[key])) > 1e-12
        for raw, research in zip(rows, research_rows, strict=True) for key in ("open", "high", "low", "close")
    )
    raw_overlay_allowed = not price_basis_changed and continuity_issue is None and len(rows) == len(research_rows)
    series = [
        {**row, "indicators": research_series[index]["indicators"] if raw_overlay_allowed else {},
         "history_issue": continuity_issue}
        for index, row in enumerate(rows)
    ]
    now = as_of.astimezone(SHANGHAI)
    for row in series:
        row["is_partial"] = str(row["date"])[:10] == now.date().isoformat() and now.time() < time(15, 15)
    for row in research_series:
        row["is_partial"] = str(row["date"])[:10] == now.date().isoformat() and now.time() < time(15, 15)
    basis_descriptor = build_research_price_basis(
        code,
        adjust,
        effective_through=as_of.date(),
        consider_corporate_actions=settings.market_provider != "mock",
    )
    research_price_basis = str(basis_descriptor["basis"])
    research_price_basis_id = str(basis_descriptor["price_basis_id"])
    basis_events = list(basis_descriptor.get("effective_evidence_ids", []))
    quality_hashes = {item.trade_date.isoformat(): item.quality_hash for item in stored}
    input_rows = []
    for item in rows:
        input_row = {key: item.get(key) for key in ("date", "open", "high", "low", "close", "volume", "amount", "source")}
        input_row["quality_hash"] = None if item.get("is_provisional") else quality_hashes.get(item["date"][:10])
        if item.get("is_provisional") and provisional is not None:
            input_row["provisional_id"] = provisional.id
        input_rows.append(input_row)
    input_hash = stable_hash({"ts_code": code, "adjust": adjust, "rows": input_rows})
    series_id = stable_hash({"base_input_hash": input_hash, "interval": interval,
                             "research_price_basis_id": research_price_basis_id,
                             "indicator_version": strategy["indicator_version"],
                             "chart_contract_version": "chart-read-v1.2.0"})
    snapshot = db.scalar(select(IndicatorSnapshot).where(IndicatorSnapshot.instrument_id == inst.id).order_by(IndicatorSnapshot.as_of_date.desc(), IndicatorSnapshot.generated_at.desc(), IndicatorSnapshot.id.desc()).limit(1))
    matches = None
    if snapshot and research_series and iso(snapshot.as_of_date) == research_series[-1]["date"]:
        values = snapshot.values_json or {}
        comparable = [key for key in CORE_FIELDS if number(values.get(key)) is not None and research_series[-1]["indicators"].get(key) is not None]
        matches = all(abs(float(values[key]) - research_series[-1]["indicators"][key]) <= (0.011 if key.startswith(("kdj", "rsi")) else 0.00011) for key in comparable) if comparable else None
    mock = settings.market_provider == "mock" or any("mock" in str(row["source"]).lower() for row in rows)
    sr_snapshot = SupportResistanceService(settings).latest(db, inst.id)
    sr = sr_snapshot
    structure_status = {"qualified": False, "reason": "snapshot_missing_requires_task", "boxes": [], "actionable": False, "interval": "1d"}
    if sr_snapshot is not None:
        structure_status = dict(sr_snapshot.get("structures") or structure_status)
        structure_status["boxes"] = [dict(box) for box in structure_status.get("boxes", [])]
        snapshot_day = sr_snapshot.get("source_as_of_date")
        if continuity_issue:
            structure_status.update(qualified=False, reason="history_qualification_blocked", boxes=[])
        elif snapshot_day and snapshot_day > as_of.date().isoformat():
            structure_status.update(qualified=False, reason="snapshot_after_as_of", boxes=[])
        elif structure_status.get("price_basis_id") != research_price_basis_id:
            structure_status.update(qualified=False, reason="price_basis_mismatch", boxes=[])
        if structure_status.get("qualified") and provisional_status.get("used_for_derived_values") and provisional_bar:
            for box in structure_status["boxes"]:
                tolerance = number(box.get("confirmation_tolerance"))
                high, low = number(provisional_bar.get("high")), number(provisional_bar.get("low"))
                if tolerance is None or high is None or low is None:
                    continue
                above, below = high > box["upper"] + tolerance, low < box["lower"] - tolerance
                if above or below:
                    box["intraday_state"] = {"state": "breakout_attempt", "side": "both" if above and below else "upper" if above else "lower",
                        "observed_at": provisional_bar.get("date"), "source_id": stable_hash({"provisional_id": provisional.id, "structure_id": box["structure_id"]})}
    structure_status["read_as_of"] = iso(as_of)
    structure_status["interval"] = "1d"
    price_only = legacy_units or any(row["volume"] is None for row in rows)
    if price_only or continuity_issue or not raw_overlay_allowed:
        sr = None
    latest_raw_close = number(rows[-1]["close"]) if rows else None
    latest_research_close = number(research_rows[-1]["close"]) if research_rows else None
    research_cost_overlay_allowed = adjust == "none" and latest_raw_close is not None and latest_research_close is not None and abs(latest_raw_close - latest_research_close) <= 1e-12
    return {
        "ts_code": code, "interval": interval, "available": bool(series), "bars": series[-limit:],
        "research_bars": research_series[-limit:],
        "reason": "history_qualification_blocked" if continuity_issue else None,
        "adjust": adjust, "currency": "CNY", "source_bars": len(rows), "history_truncated": truncated,
        "indicator_version": strategy["indicator_version"], "indicator_basis": "shared_python_core_formulas_on_research_price_series",
        "input_hash": input_hash, "series_id": series_id,
        "chart_contract_version": "chart-read-v1.2.0", "display_price_basis": f"source_adjustment:{adjust}",
        "research_price_basis": research_price_basis, "research_price_basis_id": research_price_basis_id,
        "research_basis_evidence_ids": basis_events, "raw_overlay_allowed": raw_overlay_allowed,
        "raw_overlay_reason": "history_qualification_blocked" if continuity_issue else "price_basis_mismatch" if price_basis_changed else None,
        "core_snapshot_match": matches, "source_as_of": rows[-1]["date"] if rows else None,
        "as_of": iso(as_of), "computed_at": iso(datetime.now(SHANGHAI)),
        "history_issue": continuity_issue, "return_basis": "unadjusted_price_not_total_return" if adjust == "none" else adjust,
        "qualification": continuity_issue if continuity_issue else "mock" if mock else "legacy_units_unverified" if legacy_units else "historical_price_only" if price_only else "research_only", "actionable": False,
        "cost_overlay_allowed": adjust == "none", "research_cost_overlay_allowed": research_cost_overlay_allowed,
        "sr_overlay_allowed": raw_overlay_allowed and len(adjustments) == 1 and bool(sr),
        "support_resistance": sr if raw_overlay_allowed and len(adjustments) == 1 else None,
        "price_structures": structure_status if raw_overlay_allowed else {**structure_status, "qualified": False, "reason": "price_basis_mismatch", "boxes": []},
        "research_price_structures": structure_status,
        "indicator_note": "拆分调整研究序列与原始行情的价格口径不同；原始图已隐藏未映射的指标和支撑压力，切换到研究序列可查看。" if price_basis_changed else "盘中指标基于临时行情计算，收盘后由正式日线替换；不生成操作级信号。" if provisional_status.get("used_for_derived_values") else "历史价格指标可展示；量能缺失或旧单位未验证，禁止生成操作级信号。" if price_only else "图表由服务端统一公式生成；支撑压力为当前快照，不是历史当时已知的点位。",
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
    from app.providers.data_contract import price_history_issue
    grouped = {code: [] for code in codes}
    for code, bar in pairs:
        grouped[code].append(bar)
    history_issues = {code: issue for code, bars in grouped.items()
                      if (issue := price_history_issue(list(reversed(bars))[-121:]))}
    records = [{"code": code, "date": bar.trade_date, "close": bar.close} for code, bar in pairs
               if code not in history_issues]
    correlations = [{"left": left, "right": right, "correlation": None, "observations": 0,
                     "reason": "history_not_qualified"} for i, left in enumerate(codes)
                    for right in codes[i+1:] if left in history_issues or right in history_issues]
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
    return {"pricing_complete": portfolio["pricing_complete"], "max_weight": max((item["weight"] or 0 for item in items), default=0) if portfolio["pricing_complete"] else None, "theme_weights": theme_weights, "correlations": correlations, "history_issues": history_issues, "basis": "last_120_daily_return_pearson_unadjusted_research", "limitations": ["不含未录入现金和资产", "收益相关性不是成分股重叠", "未复权收益会受分红影响", "个人成本不参与共享市场信号"], "actionable": False}


def sector_overview(db: Session, settings: Settings) -> dict:
    """Two bounded read-only SQL queries; no all-market grade/indicator hydration."""
    ranked = select(SectorSnapshot.id, func.row_number().over(partition_by=[SectorSnapshot.board_type, SectorSnapshot.sector_name], order_by=[SectorSnapshot.trade_date.desc(), SectorSnapshot.fetched_at.desc(), SectorSnapshot.id.desc()]).label("rn")).subquery()
    rows = db.scalars(select(SectorSnapshot).join(ranked, ranked.c.id == SectorSnapshot.id).where(ranked.c.rn == 1).order_by(SectorSnapshot.board_type, SectorSnapshot.sector_name).limit(2000)).all()
    boards = []
    for row in rows:
        total = row.total_count or 0
        valid_breadth = total > 0 and sum((row.up_count or 0, row.down_count or 0, row.flat_count or 0)) == total
        boards.append({"board_type": row.board_type, "sector_name": row.sector_name, "sector_pct_change": number(row.pct_change), "source": row.source, "source_as_of": iso(row.trade_date), "fetched_at": iso(row.fetched_at), "is_mock": settings.market_provider == "mock" or "mock" in row.source.lower(), "breadth": {"trade_date": iso(row.trade_date), "available": valid_breadth, "up": row.up_count if valid_breadth else None, "down": row.down_count if valid_breadth else None, "flat": row.flat_count if valid_breadth else None, "total": total if valid_breadth else None}})
    return {"boards": boards, "scope": "persisted_sector_snapshots", "pct_change_unit": "percentage_points", "source_as_of": max((iso(row.trade_date) for row in rows), default=None), "freshness": "read_source_dates_not_live" if rows else "missing", "actionable": False}
