from __future__ import annotations

from app.core.config import Settings, get_settings
from app.providers.akshare import AKShareProvider
from app.providers.base import CapabilityUnavailable, MarketProvider, ProviderError
from app.providers.composite import CompositeProvider
from app.providers.ftshare import FTShareProvider
from app.providers.mock import MockProvider
from app.providers.rss_news import RssNewsProvider
from app.providers.tushare import TushareProvider


def build_provider(settings: Settings | None = None) -> MarketProvider:
    settings = settings or get_settings()
    if settings.market_provider == "mock":
        return MockProvider(settings)
    if settings.market_provider == "tushare":
        return TushareProvider(settings)
    if settings.market_provider == "akshare":
        return AKShareProvider(settings)
    if settings.market_provider == "ftshare":
        if not (settings.ftshare_enabled and settings.ftshare_qualification == "qualified"):
            raise CapabilityUnavailable("FTShare provider is disabled or unqualified")
        return FTShareProvider(settings)

    providers: list[MarketProvider] = []
    errors: list[str] = []
    if settings.market_provider == "public_composite":
        # The usable/free tier keeps AKShare as the primary public source.  A
        # configured Tushare token is an explicit second candidate for the
        # same tier, so a transient upstream block does not force the user to
        # switch tiers; the complete tier below intentionally remains
        # Tushare-first.
        provider_classes = [AKShareProvider]
        if settings.tushare_token:
            provider_classes.append(TushareProvider)
        provider_classes.append(FTShareProvider)
    else:
        provider_classes = (TushareProvider, AKShareProvider, FTShareProvider)
    for provider_cls in provider_classes:
        if provider_cls is FTShareProvider and not (
            settings.ftshare_enabled and settings.ftshare_qualification == "qualified"
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
