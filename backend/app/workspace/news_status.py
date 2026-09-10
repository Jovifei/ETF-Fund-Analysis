"""Public publication age and collector health; no network calls or feed URLs."""
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.core.config import Settings, get_settings
from app.models import NewsItem
from app.workspace.models import WorkspaceDataJob


def _market_time(value: datetime | None, settings: Settings) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=settings.timezone)


def _utc_time(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC)


def read(db, settings: Settings | None = None):
    settings = settings or get_settings()
    now = datetime.now(UTC)
    rows = db.execute(
        select(
            NewsItem.source,
            func.count(),
            func.max(NewsItem.published_at),
            func.max(NewsItem.fetched_at),
        )
        .group_by(NewsItem.source)
        .limit(100)
    ).all()
    sources = []
    for source, count, published, fetched in rows:
        publication = _market_time(published, settings)
        publication_utc = publication.astimezone(UTC) if publication else None
        age_seconds = (now - publication_utc).total_seconds() if publication_utc else None
        age_hours = round(age_seconds / 3600, 1) if age_seconds is not None and age_seconds >= 0 else None
        sources.append(
            {
                "source": source,
                "count": count,
                "latest_published_at": publication.isoformat() if publication else None,
                "last_fetched_at": _utc_time(fetched).isoformat() if fetched else None,
                "age_hours": age_hours,
                "freshness": (
                    "older_than_24h"
                    if age_hours is not None and age_hours > 24
                    else "within_24h"
                    if age_hours is not None
                    else "unknown"
                ),
            }
        )
    task = db.scalar(
        select(WorkspaceDataJob)
        .where(WorkspaceDataJob.request_json["task"].as_string().in_(["news", "refresh"]))
        .order_by(WorkspaceDataJob.created_at.desc())
        .limit(1)
    )
    return {
        "sources": sources,
        "as_of": now.isoformat(),
        "provider_called": False,
        "task": None
        if task is None
        else {
            "status": task.status,
            "created_at": task.created_at.isoformat(),
            "finished_at": task.finished_at.isoformat() if task.finished_at else None,
            "steps": [
                {key: step.get(key) for key in ("task", "status", "reason")}
                for step in (task.result_json or {}).get("steps", [])
                if step.get("task") == "refresh_news"
            ],
        },
        "note": "24小时标记只是发布时间年龄，不是今日全量覆盖证明。抓取成功可以返回旧消息；重新读取页面不会抓取新消息。",
    }
