"""Configuration and observed coverage are separate; this endpoint never probes.

The response is an administrative projection, not a copy of Settings or audits.
It contains no credential values, source URLs, raw failure messages or accounts.
"""
from __future__ import annotations

import importlib.util
from datetime import UTC, datetime

from sqlalchemy import case, func, select

from app.models import DailyBar, Instrument, MarketBar, ProviderAudit, QuoteSnapshot, RuntimeSetting
from app.providers.data_contract import LEGACY_SOURCES, VERSION
from app.workspace.models import WorkspaceDataJob


def configuration(db, settings) -> dict:
    # Never use RuntimeService.get_all/resolve_settings here: these historically
    # ensure and write defaults even on a GET. Mirror the existing tier contract.
    raw = dict(db.execute(select(RuntimeSetting.key, RuntimeSetting.value_json).where(
        RuntimeSetting.key.in_(("market_data_tier", "tushare_token")))).all())
    stored = raw.get("tushare_token")
    stored_set = isinstance(stored, str) and bool(stored.strip())
    token_set = stored_set or bool(settings.tushare_token.strip())
    tier = raw.get("market_data_tier") or ("complete" if settings.market_provider in {"composite", "tushare"} else "usable")
    mode = settings.market_provider
    ft = settings.ftshare_enabled and settings.ftshare_qualification == "qualified"
    if mode not in {"mock", "ftshare", "public_composite"}:
        mode = "composite" if tier == "complete" and token_set else "public_composite" if token_set or ft else "akshare"
    return {"configured_provider": settings.market_provider, "effective_provider": mode,
        "tier": tier, "tushare_configured": token_set,
        "credential_origin": "legacy_database" if stored_set else "environment" if token_set else "missing",
        "legacy_secret_storage": stored_set, "ftshare_eligible": bool(ft)}


def _iso(value):
    return value.isoformat() if value is not None else None


def inspect_sources(db, settings) -> dict:
    config = configuration(db, settings)
    ak = importlib.util.find_spec("akshare") is not None
    rss = bool(settings.news_rss_urls.strip())
    sources = [
        {"id": "tushare", "configured": config["tushare_configured"], "installed": True,
         "transport": "fixed_https_bounded_child", "deadline_seconds": settings.tushare_timeout_seconds,
         "status": "permission_not_verified" if config["tushare_configured"] else "credentials_missing",
         "capabilities": {"catalog": "fund_basic", "daily": "fund_daily", "quote": "rt_etf_k", "minutes": "etf_mins_30m_60m", "news": "permission_dependent"},
         "notes": ["日线、分钟、实时和新闻权限分开，Token 存在不等于授权成功", "沪市实时查询带 HQ_FND_TICK；要求源时间，不拼接今天日期"]},
        {"id": "akshare", "configured": True, "installed": ak, "deadline_seconds": settings.akshare_timeout_seconds,
         "status": "public_source_not_verified" if ak else "package_missing",
         "capabilities": {"catalog": "public_spot_catalog", "daily": "eastmoney_then_sina", "quote": "unverified_public_snapshot", "minutes": "not_connected", "news": "public_news"},
         "notes": ["免费公开接口可能限流、拒绝或变更", "公开现价仅供研究；无可靠源时间不标实时", "Sina 日线作为价格回退；成交量单位未独立验证，暂留空"]},
        {"id": "ftshare", "configured": settings.ftshare_enabled, "installed": True,
         "status": "qualified_config_only" if config["ftshare_eligible"] else "disabled" if not settings.ftshare_enabled else "unqualified",
         "capabilities": {"catalog": "gated", "daily": "gated", "quote": "gated", "minutes": "not_connected", "news": "not_connected"},
         "notes": ["仅显式 enabled 且 qualified 才能进入回退链；本版本不提升资格"]},
        {"id": "rss", "configured": rss, "installed": importlib.util.find_spec("feedparser") is not None,
         "status": "source_not_verified" if rss else "sources_missing",
         "capabilities": {"news": "configured_feeds_only"}, "notes": ["仅配置的公开来源，保留原文发布时间；不回显来源地址"]},
        {"id": "mock", "configured": config["effective_provider"] == "mock", "installed": True,
         "status": "demo_only", "capabilities": {"all": "synthetic_test_only"}, "notes": ["不与真实数据静默混用，始终 actionable=false"]},
    ]
    daily = [{"source": source, "rows": count, "instruments": instruments, "first_date": _iso(first), "last_date": _iso(last)}
        for source, count, instruments, first, last in db.execute(select(DailyBar.source, func.count(), func.count(func.distinct(DailyBar.instrument_id)), func.min(DailyBar.trade_date), func.max(DailyBar.trade_date)).group_by(DailyBar.source))]
    quote = [{"source": source, "rows": count, "last_source_time": _iso(observed), "last_fetch_time": _iso(fetched)}
        for source, count, observed, fetched in db.execute(select(QuoteSnapshot.source, func.count(), func.max(case((QuoteSnapshot.timestamp_verified.is_(True), QuoteSnapshot.quote_time), else_=None)), func.max(QuoteSnapshot.fetched_at)).group_by(QuoteSnapshot.source))]
    minutes = [{"interval": interval, "rows": count, "last_time": _iso(last)} for interval, count, last in db.execute(
        select(MarketBar.interval, func.count(), func.max(MarketBar.bar_time)).group_by(MarketBar.interval))]
    audits = list(db.scalars(select(ProviderAudit).order_by(ProviderAudit.created_at.desc(), ProviderAudit.id.desc()).limit(25)))
    recent = [{"provider": row.provider, "operation": row.operation, "status": row.status,
        "record_count": row.record_count, "latency_ms": row.latency_ms, "observed_at": _iso(row.created_at)} for row in audits]
    active = db.scalar(select(func.count()).select_from(Instrument).where(Instrument.enabled.is_(True))) or 0
    legacy = db.scalar(select(func.count()).select_from(DailyBar).join(Instrument, Instrument.id == DailyBar.instrument_id).where(Instrument.enabled.is_(True), DailyBar.source.in_(LEGACY_SOURCES))) or 0
    last_job = db.scalar(select(WorkspaceDataJob).order_by(WorkspaceDataJob.created_at.desc()).limit(1))
    return {"as_of": datetime.now(UTC).isoformat(), **config, "data_contract_version": VERSION,
        "provider_called": False, "actionable": False, "sources": sources,
        "minute_sync_enabled": settings.minute_bars_enabled, "tracked_instruments": active,
        "legacy_history_rows": legacy, "history_repair_required": legacy > 0,
        "coverage": {"daily": daily, "quotes": quote, "minutes": minutes}, "recent_audits": recent,
        "last_data_job": {"job_id": last_job.job_id, "status": last_job.status} if last_job else None,
        "notes": ["配置状态不是连接成功；覆盖率来自已入库记录，不能证明本机/生产网络可用", "日线数据与模型资格分开，历史 14:30 回测仍未取得资格", "旧单位数据先完整重抓再原子替换，禁止直接乘系数猜测修复"]}
