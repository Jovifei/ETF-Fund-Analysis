from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings, get_settings


@dataclass(slots=True)
class ThemeMatch:
    theme_l1: str
    theme_l2: str
    style_tags: list[str]
    exposure_keys: list[str]
    confidence: str
    matched_keyword: str | None = None


class ThemeClassifier:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.taxonomy = self.settings.load_taxonomy()

    def classify(self, text: str) -> list[ThemeMatch]:
        normalized = (text or "").strip()
        matches: list[ThemeMatch] = []
        for exact, value in self.taxonomy.get("exact", {}).items():
            if exact in normalized:
                matches.append(
                    ThemeMatch(
                        theme_l1=value["theme_l1"],
                        theme_l2=value["theme_l2"],
                        style_tags=list(value.get("style_tags", [])),
                        exposure_keys=list(value.get("exposure_keys", [])),
                        confidence="high",
                        matched_keyword=exact,
                    )
                )
        for rule in self.taxonomy.get("keyword_rules", []):
            keyword = next((item for item in rule.get("keywords", []) if item.lower() in normalized.lower()), None)
            if keyword:
                candidate = ThemeMatch(
                    theme_l1=rule["theme_l1"],
                    theme_l2=rule["theme_l2"],
                    style_tags=list(rule.get("style_tags", [])),
                    exposure_keys=list(rule.get("exposure_keys", [])),
                    confidence="medium",
                    matched_keyword=keyword,
                )
                if not any(item.theme_l2 == candidate.theme_l2 for item in matches):
                    matches.append(candidate)
        return matches
