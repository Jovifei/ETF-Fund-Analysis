from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import RuntimeSetting


DEFAULT_KEYS = {
    "quote_refresh_minutes": "盘中行情刷新分钟数",
    "signal_refresh_minutes": "盘中信号重算分钟数",
    "news_refresh_minutes": "普通新闻刷新分钟数",
    "lunch_news_refresh_minutes": "午间新闻刷新分钟数",
    "signal_center_coefficient": "信号中心敏感度系数（0.5-1.5，仅作用研究视图）",
}

FLOAT_KEYS = {
    "signal_center_coefficient": (0.5, 1.5),
}


class RuntimeService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.strategy = self.settings.load_strategy()

    def _default_coefficient(self) -> float:
        config = self.strategy.get("signal_center", {}).get("coefficient", {})
        return float(config.get("default", 1.0))

    def ensure_defaults(self, db: Session) -> None:
        values = {
            "quote_refresh_minutes": self.settings.quote_refresh_minutes,
            "signal_refresh_minutes": self.settings.signal_refresh_minutes,
            "news_refresh_minutes": self.settings.news_refresh_minutes,
            "lunch_news_refresh_minutes": self.settings.lunch_news_refresh_minutes,
            "signal_center_coefficient": self._default_coefficient(),
        }
        for key, value in values.items():
            existing = db.get(RuntimeSetting, key)
            if not existing:
                db.add(RuntimeSetting(key=key, value_json=value, description=DEFAULT_KEYS[key]))
        db.flush()

    def get_all(self, db: Session) -> dict[str, Any]:
        self.ensure_defaults(db)
        rows = db.scalars(select(RuntimeSetting)).all()
        return {row.key: row.value_json for row in rows}

    def update(self, db: Session, updates: dict[str, Any]) -> dict[str, Any]:
        validators = {
            "quote_refresh_minutes": (1, 60),
            "signal_refresh_minutes": (5, 120),
            "news_refresh_minutes": (5, 240),
            "lunch_news_refresh_minutes": (3, 120),
        }
        for key, value in updates.items():
            if key in FLOAT_KEYS:
                lower, upper = FLOAT_KEYS[key]
                float_value = round(float(value), 2)
                if not lower <= float_value <= upper:
                    raise ValueError(f"{key} 必须在 {lower}-{upper}")
                row = db.get(RuntimeSetting, key)
                if row:
                    row.value_json = float_value
                else:
                    db.add(
                        RuntimeSetting(key=key, value_json=float_value, description=DEFAULT_KEYS[key])
                    )
                continue
            if key not in validators:
                continue
            lower, upper = validators[key]
            int_value = int(value)
            if not lower <= int_value <= upper:
                raise ValueError(f"{key} 必须在 {lower}-{upper}")
            row = db.get(RuntimeSetting, key)
            if row:
                row.value_json = int_value
            else:
                db.add(RuntimeSetting(key=key, value_json=int_value, description=DEFAULT_KEYS[key]))
        db.flush()
        return self.get_all(db)
