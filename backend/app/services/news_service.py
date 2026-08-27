from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import NewsItem
from app.providers.base import MarketProvider
from app.services.audit_service import AuditTimer, record_provider_audit
from app.services.event_service import emit_event
from app.services.llm_service import NewsAnalysis, OpenAICompatibleClient
from app.services.theme_service import ThemeClassifier
from app.utils.hashing import stable_hash
from app.utils.numbers import clamp


POSITIVE_WORDS = ["利好", "增长", "突破", "提振", "回升", "上调", "支持", "加速", "改善", "创新"]
NEGATIVE_WORDS = ["利空", "下降", "下调", "风险", "处罚", "收紧", "减产", "亏损", "波动", "分歧"]


class NewsService:
    def __init__(self, provider: MarketProvider, settings: Settings | None = None) -> None:
        self.provider = provider
        self.settings = settings or get_settings()
        self.classifier = ThemeClassifier(self.settings)
        self.llm = OpenAICompatibleClient(self.settings)

    def _heuristic_analysis(self, title: str, summary: str | None) -> NewsAnalysis:
        text = f"{title} {summary or ''}"
        theme_matches = self.classifier.classify(text)
        positive = sum(text.count(word) for word in POSITIVE_WORDS)
        negative = sum(text.count(word) for word in NEGATIVE_WORDS)
        raw_score = clamp((positive - negative) / max(3, positive + negative), -1, 1)
        if raw_score > 0.15:
            direction = "positive"
        elif raw_score < -0.15:
            direction = "negative"
        elif positive or negative:
            direction = "mixed"
        else:
            direction = "neutral"
        return NewsAnalysis(
            facts=[title],
            inferences=[],
            risk_flags=["仅基于标题与可用摘要，需结合行情验证"] if summary is None else [],
            affected_themes=[item.theme_l2 for item in theme_matches],
            impact_direction=direction,
            impact_horizon="1w",
            impact_score=float(raw_score),
        )

    def refresh(self, db: Session, since_hours: int = 30, run_id: str | None = None) -> dict:
        run_id = run_id or uuid4().hex
        timer = AuditTimer()
        error: Exception | None = None
        records = []
        try:
            records = self.provider.fetch_news(since_hours)
        except Exception as exc:
            error = exc
            records = []
        finally:
            record_provider_audit(
                db,
                run_id=run_id,
                operation="fetch_news",
                provider=self.provider,
                result=records,
                error=error,
                latency_ms=timer.elapsed_ms,
            )
        inserted = 0
        updated = 0
        llm_count = 0
        for record in records:
            existing = db.scalar(
                select(NewsItem).where(
                    NewsItem.source == record.source,
                    NewsItem.source_id == record.source_id,
                )
            )
            heuristic = self._heuristic_analysis(record.title, record.summary)
            llm_result = self.llm.analyze_news(
                record.title,
                record.summary,
                heuristic.affected_themes,
            )
            analysis = llm_result or heuristic
            llm_count += int(llm_result is not None)
            payload = {
                **record.to_dict(),
                "analysis": analysis.model_dump(),
            }
            if existing is None:
                existing = NewsItem(
                    source=record.source,
                    source_id=record.source_id,
                    title=record.title,
                    published_at=record.published_at,
                    quality_hash=stable_hash(payload),
                )
                db.add(existing)
                inserted += 1
            else:
                updated += 1
            existing.title = record.title
            existing.summary = record.summary
            existing.url = record.url
            existing.published_at = record.published_at
            existing.facts_json = analysis.facts
            existing.inferences_json = analysis.inferences
            existing.risk_flags_json = analysis.risk_flags
            existing.affected_themes_json = analysis.affected_themes
            existing.impact_direction = analysis.impact_direction
            existing.impact_horizon = analysis.impact_horizon
            existing.impact_score = analysis.impact_score
            existing.llm_model = self.settings.llm_model if llm_result else None
            existing.quality_hash = stable_hash(payload)
        db.flush()
        emit_event(
            db,
            "news.updated",
            {"run_id": run_id, "inserted": inserted, "updated": updated, "llm_count": llm_count},
        )
        return {
            "run_id": run_id,
            "inserted": inserted,
            "updated": updated,
            "llm_count": llm_count,
            "provider_error": f"{type(error).__name__}: {error}" if error else None,
        }
