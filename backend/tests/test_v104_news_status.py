from datetime import UTC, datetime

from app.core.config import Settings
from app.models import NewsItem
from app.workspace import news_status


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        value = datetime(2026, 9, 10, 0, 0, tzinfo=UTC)
        return value if tz is not None else value.replace(tzinfo=None)


def test_news_status_uses_market_timezone_for_naive_publication_and_utc_for_fetch(
    db_session, monkeypatch
):
    db_session.add(
        NewsItem(
            source="status-naive",
            source_id="naive-1",
            title="naive publication",
            published_at=datetime(2026, 9, 10, 7, 0),
            fetched_at=datetime(2026, 9, 9, 23, 0),
            quality_hash="a" * 64,
        )
    )
    db_session.flush()
    monkeypatch.setattr(news_status, "datetime", FrozenDateTime)

    result = news_status.read(db_session, settings=Settings(_env_file=None, timezone_name="Asia/Shanghai"))
    item = next(row for row in result["sources"] if row["source"] == "status-naive")

    assert item["latest_published_at"] == "2026-09-10T07:00:00+08:00"
    assert item["last_fetched_at"] == "2026-09-09T23:00:00+00:00"
    assert item["age_hours"] == 1.0
    assert item["freshness"] == "within_24h"


def test_news_status_preserves_aware_publication_timezone():
    settings = Settings(_env_file=None, timezone_name="Asia/Shanghai")
    aware = datetime(2026, 9, 9, 23, 0, tzinfo=UTC)

    assert news_status._market_time(aware, settings).isoformat() == "2026-09-09T23:00:00+00:00"
    assert news_status._utc_time(aware).isoformat() == "2026-09-09T23:00:00+00:00"


def test_news_status_does_not_turn_future_publication_into_zero_age(db_session, monkeypatch):
    db_session.add(
        NewsItem(
            source="status-future",
            source_id="future-1",
            title="future publication",
            published_at=datetime(2026, 9, 10, 9, 0),
            fetched_at=datetime(2026, 9, 9, 23, 0),
            quality_hash="c" * 64,
        )
    )
    db_session.flush()
    monkeypatch.setattr(news_status, "datetime", FrozenDateTime)

    result = news_status.read(db_session, settings=Settings(_env_file=None, timezone_name="Asia/Shanghai"))
    item = next(row for row in result["sources"] if row["source"] == "status-future")

    assert item["age_hours"] is None
    assert item["freshness"] == "unknown"
