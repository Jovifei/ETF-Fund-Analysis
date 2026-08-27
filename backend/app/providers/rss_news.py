from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx

from app.core.config import Settings, get_settings
from app.providers.base import CapabilityUnavailable, MarketProvider, ProviderError
from app.providers.types import BarRecord, InstrumentRecord, NewsRecord, QuoteRecord

logger = logging.getLogger(__name__)


class RssNewsProvider(MarketProvider):
    """Optional RSS/Atom news provider.

    URLs are operator-supplied through NEWS_RSS_URLS. This keeps the application
    independent from any particular publisher and works with a self-hosted RSSHub
    instance as well as ordinary RSS/Atom feeds.
    """

    name = "rss"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.urls = self.settings.news_rss_url_list
        if not self.urls:
            raise ProviderError("NEWS_RSS_URLS 未配置")
        try:
            import feedparser  # type: ignore
        except ImportError as exc:
            raise ProviderError("未安装 feedparser；请安装 market 可选依赖") from exc
        self.feedparser = feedparser
        self.tz = ZoneInfo(self.settings.timezone_name)
        for raw in self.urls:
            parsed = urlparse(raw)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ProviderError(f"非法 RSS URL：{raw}")

    def list_instruments(self, codes: list[str] | None = None) -> list[InstrumentRecord]:
        raise CapabilityUnavailable("RSS provider 不提供标的列表")

    def fetch_daily_bars(self, ts_code: str, start_date: date, end_date: date) -> list[BarRecord]:
        raise CapabilityUnavailable("RSS provider 不提供 K 线")

    def fetch_spot_quotes(self, codes: list[str]) -> list[QuoteRecord]:
        raise CapabilityUnavailable("RSS provider 不提供行情")

    def _published_at(self, entry: dict) -> datetime:
        value = entry.get("published") or entry.get("updated") or entry.get("created")
        if value:
            try:
                parsed = parsedate_to_datetime(str(value))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=self.tz)
                return parsed.astimezone(self.tz)
            except (TypeError, ValueError, OverflowError):
                pass
        parsed_tuple = entry.get("published_parsed") or entry.get("updated_parsed")
        if parsed_tuple:
            try:
                return datetime(*parsed_tuple[:6], tzinfo=self.tz)
            except (TypeError, ValueError):
                pass
        return datetime.now(self.tz)

    def fetch_news(self, since_hours: int = 24) -> list[NewsRecord]:
        now = datetime.now(self.tz)
        cutoff = now.timestamp() - max(1, since_hours) * 3600
        records: list[NewsRecord] = []
        errors: list[str] = []
        headers = {
            "User-Agent": "china-fund-decision/0.2 (+private research; RSS reader)",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        }
        with httpx.Client(timeout=self.settings.news_rss_timeout_seconds, follow_redirects=True) as client:
            for url in self.urls:
                try:
                    response = client.get(url, headers=headers)
                    response.raise_for_status()
                    parsed = self.feedparser.parse(response.content)
                    feed_title = str(parsed.feed.get("title") or urlparse(url).netloc)
                    for entry in parsed.entries:
                        item = dict(entry)
                        title = str(item.get("title") or "").strip()
                        if not title:
                            continue
                        published_at = self._published_at(item)
                        if published_at.timestamp() < cutoff:
                            continue
                        link = str(item.get("link") or "").strip() or None
                        summary = str(item.get("summary") or item.get("description") or "").strip() or None
                        raw_id = str(item.get("id") or item.get("guid") or link or f"{title}|{published_at.isoformat()}")
                        source_id = hashlib.sha256(f"{url}|{raw_id}".encode("utf-8")).hexdigest()
                        records.append(
                            NewsRecord(
                                source=f"rss:{feed_title}"[:64],
                                source_id=source_id,
                                title=title[:500],
                                summary=summary[:4000] if summary else None,
                                url=link,
                                published_at=published_at,
                            )
                        )
                except Exception as exc:  # one failed feed must not suppress the others
                    message = f"{url}: {type(exc).__name__}: {exc}"
                    errors.append(message)
                    logger.warning("RSS feed failed: %s", message)
        if not records and errors and len(errors) == len(self.urls):
            raise ProviderError("所有 RSS 源均失败；" + "; ".join(errors))
        unique: dict[tuple[str, str], NewsRecord] = {}
        for item in records:
            unique[(item.source, item.source_id)] = item
        return sorted(unique.values(), key=lambda item: item.published_at, reverse=True)
