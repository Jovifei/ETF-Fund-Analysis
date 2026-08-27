from __future__ import annotations

from app.core.config import Settings, get_settings
from app.providers.akshare import AKShareProvider
from app.providers.base import MarketProvider, ProviderError
from app.providers.composite import CompositeProvider
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

    providers: list[MarketProvider] = []
    errors: list[str] = []
    for provider_cls in (TushareProvider, AKShareProvider):
        try:
            providers.append(provider_cls(settings))
        except Exception as exc:
            errors.append(f"{provider_cls.__name__}: {exc}")
    if settings.news_rss_url_list:
        try:
            providers.append(RssNewsProvider(settings))
        except Exception as exc:
            errors.append(f"RssNewsProvider: {exc}")
    if settings.allow_mock_fallback:
        providers.append(MockProvider(settings))
    if not providers:
        raise ProviderError("无法初始化任何数据源；" + "; ".join(errors))
    return CompositeProvider(providers)

# Backward-compatible descriptive alias used by the task and scheduler layers.
create_provider = build_provider
