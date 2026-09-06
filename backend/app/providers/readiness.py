"""Sanitized, non-network data-source readiness for local operators.

This is deliberately a preflight, not a health claim.  It checks configured
selection, installed optional dependencies and explicit qualification flags;
the bounded qualification command remains the evidence for an upstream call.
"""
from __future__ import annotations

from importlib.util import find_spec
from typing import Any

from app.core.config import Settings


def module_available(name: str) -> bool:
    return find_spec(name) is not None


def _status(*, dependency: bool, configured: bool = True, blocked: str | None = None) -> str:
    if blocked:
        return blocked
    if not configured:
        return "not_configured"
    return "ready_unprobed" if dependency else "missing_dependency"


def _source(
    source_id: str,
    status: str,
    capabilities: dict[str, bool],
    note: str,
) -> dict[str, Any]:
    return {"id": source_id, "status": status, "capabilities": capabilities, "note": note}


def source_readiness(settings: Settings) -> dict[str, Any]:
    """Return only boolean configuration facts and never a credential value."""
    tushare_available = module_available("tushare")
    akshare_available = module_available("akshare")
    feedparser_available = module_available("feedparser")
    token_set = bool(settings.tushare_token.strip())

    tushare_status = _status(
        dependency=tushare_available,
        blocked="missing_token" if not token_set else None,
    )
    akshare_status = _status(dependency=akshare_available)
    ftshare_status = _status(
        dependency=True,
        blocked="disabled" if not settings.ftshare_enabled else (
            "unqualified" if settings.ftshare_qualification != "qualified" else None
        ),
    )
    rss_status = _status(
        dependency=feedparser_available,
        configured=bool(settings.news_rss_url_list),
    )
    sources = [
        _source(
            "tushare",
            tushare_status,
            {"catalog": True, "daily_bars": True, "spot_quotes": True, "news": True, "trade_calendar": True},
            "需要进程环境或运行时安全设置中的 Token；状态不代表权限或网络已验证。",
        ),
        _source(
            "akshare",
            akshare_status,
            {"catalog": True, "daily_bars": True, "spot_quotes": True, "news": True, "sectors": True, "market_context": True},
            "免费公共源；日线和目录可初始化，实时行情仍须在交易时段单独资格验证。",
        ),
        _source(
            "ftshare",
            ftshare_status,
            {"catalog": True, "daily_bars": True, "spot_quotes": True},
            "只有显式启用且完成资格验证后才能进入 Provider 链。",
        ),
        _source(
            "rss",
            rss_status,
            {"news": True},
            "仅在配置受信 RSS 地址并安装可选依赖后启用；新闻必须保留来源和时间。",
        ),
    ]
    status_by_id = {item["id"]: item["status"] for item in sources}
    effective = settings.market_provider
    active = {
        "mock": [],
        "tushare": ["tushare"],
        "akshare": ["akshare"],
        "ftshare": ["ftshare"],
        "public_composite": ["akshare", "tushare", "ftshare"],
        "composite": ["tushare", "akshare", "ftshare"],
    }[effective]
    ready = {"ready_unprobed"}
    daily_sources = [source for source in active if status_by_id[source] in ready]
    return {
        "effective_provider": effective,
        "mode": "demo_only" if effective == "mock" else "real_provider_preflight",
        "tushare_token_set": token_set,
        "can_initialize_daily_bars": bool(daily_sources),
        "daily_bar_candidates": daily_sources,
        "realtime_quote_status": "not_qualified",
        "realtime_quote_note": "必须在交易时段通过带来源时间的资格检查；盘后、超时和日线退化均不可操作。",
        "sources": sources,
    }
