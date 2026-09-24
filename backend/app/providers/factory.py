from __future__ import annotations

import logging

from app.core.config import Settings, get_settings
from app.providers.akshare import AKShareProvider
from app.providers.base import CapabilityUnavailable, MarketProvider, ProviderError
from app.providers.composite import CompositeProvider
from app.providers.ftshare import FTShareProvider
from app.providers.mock import MockProvider
from app.providers.rss_news import RssNewsProvider
from app.providers.sina import SinaProvider
from app.providers.tushare import TushareProvider
from app.providers.tencent import TencentProvider


def _with_news(provider, settings):
    if settings.news_rss_url_list:
        try:
            return CompositeProvider([provider, RssNewsProvider(settings)])
        except Exception as exc:
            logging.getLogger(__name__).warning("RSS initialization unavailable: %s", type(exc).__name__)
    return provider


def build_provider(settings: Settings | None = None) -> MarketProvider:
    settings = settings or get_settings()
    if settings.market_provider == "mock":
        return MockProvider(settings)
    if settings.market_provider == "tushare":
        return _with_news(TushareProvider(settings), settings)
    if settings.market_provider == "akshare":
        return _with_news(AKShareProvider(settings), settings)
    if settings.market_provider == "ftshare":
        if not (settings.ftshare_enabled and (
            settings.ftshare_daily_qualification == "qualified"
            or settings.ftshare_quote_qualification == "qualified"
        )):
            raise CapabilityUnavailable("FTShare provider is disabled or unqualified")
        return _with_news(FTShareProvider(settings), settings)

    providers: list[MarketProvider] = []
    errors: list[str] = []
    if settings.market_provider == "public_composite":
        # Try public timestamped quotes before the optional permission-gated source.
        provider_classes = [AKShareProvider, SinaProvider, TencentProvider]
        if settings.tushare_token:
            provider_classes.append(TushareProvider)
        provider_classes.append(FTShareProvider)
    else:
        provider_classes = (TushareProvider, AKShareProvider, SinaProvider, TencentProvider, FTShareProvider)
    for provider_cls in provider_classes:
        if provider_cls is FTShareProvider and not (
            settings.ftshare_enabled and (
                settings.ftshare_daily_qualification == "qualified"
                or settings.ftshare_quote_qualification == "qualified"
            )
        ):
            continue
        try:
            providers.append(provider_cls(settings))
        except Exception as exc:
            errors.append(f"{provider_cls.__name__}: {type(exc).__name__}")
    if settings.news_rss_url_list:
        try:
            providers.append(RssNewsProvider(settings))
        except Exception as exc:
            errors.append(f"RssNewsProvider: {type(exc).__name__}")
    if not providers:
        raise ProviderError("无法初始化任何数据源；" + "; ".join(errors))
    return CompositeProvider(providers)

# Backward-compatible descriptive alias used by the task and scheduler layers.
create_provider = build_provider
