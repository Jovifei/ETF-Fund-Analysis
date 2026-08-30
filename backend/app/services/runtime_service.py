from __future__ import annotations

import logging
import re
import time
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import RuntimeSetting
from app.providers.factory import create_provider


DEFAULT_KEYS = {
    "quote_refresh_minutes": "盘中行情刷新分钟数",
    "signal_refresh_minutes": "盘中信号重算分钟数",
    "news_refresh_minutes": "普通新闻刷新分钟数",
    "lunch_news_refresh_minutes": "午间新闻刷新分钟数",
    "signal_center_coefficient": "信号中心敏感度系数（0.5-1.5，仅作用研究视图）",
    "market_data_tier": "行情档位：usable=免费能用，complete=更完整需 Token",
}

FLOAT_KEYS = {
    "signal_center_coefficient": (0.5, 1.5),
}

SECRET_KEYS = frozenset({"tushare_token"})
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9._-]{16,128}$")
PROBE_CODE = "510300.SH"
PROBE_LOOKBACK_DAYS = 40
TOKEN_DESCRIPTION = "Tushare Token（只写不回显）"

logger = logging.getLogger(__name__)


class RuntimeService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.strategy = self.settings.load_strategy()

    def _default_coefficient(self) -> float:
        config = self.strategy.get("signal_center", {}).get("coefficient", {})
        return float(config.get("default", 1.0))

    def _default_tier(self) -> str:
        if self.settings.market_provider in {"tushare", "composite"}:
            return "complete"
        return "usable"

    def _raw_settings(self, db: Session) -> dict[str, Any]:
        self.ensure_defaults(db)
        rows = db.scalars(select(RuntimeSetting)).all()
        return {row.key: row.value_json for row in rows}

    def _stored_token(self, db: Session) -> str:
        raw = self._raw_settings(db).get("tushare_token")
        return raw.strip() if isinstance(raw, str) else ""

    def _env_token(self) -> str:
        return (self.settings.tushare_token or "").strip()

    def _resolve_token(self, db: Session, token_override: str | None = None) -> str:
        if token_override is not None:
            return self._validated_token(token_override, allow_empty=True)
        return self._stored_token(db) or self._env_token()

    @staticmethod
    def _validated_token(value: object, *, allow_empty: bool = False) -> str:
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ValueError("tushare token rejected")
        token = value.strip()
        if not token:
            if allow_empty:
                return ""
            raise ValueError("tushare token rejected")
        if not TOKEN_PATTERN.fullmatch(token):
            raise ValueError("tushare token rejected")
        return token

    def _upsert(self, db: Session, key: str, value: Any, description: str) -> None:
        row = db.get(RuntimeSetting, key)
        if row:
            row.value_json = value
            return
        db.add(RuntimeSetting(key=key, value_json=value, description=description))

    def _clear_token(self, db: Session) -> None:
        row = db.get(RuntimeSetting, "tushare_token")
        if row:
            db.delete(row)

    def ensure_defaults(self, db: Session) -> None:
        values = {
            "quote_refresh_minutes": self.settings.quote_refresh_minutes,
            "signal_refresh_minutes": self.settings.signal_refresh_minutes,
            "news_refresh_minutes": self.settings.news_refresh_minutes,
            "lunch_news_refresh_minutes": self.settings.lunch_news_refresh_minutes,
            "signal_center_coefficient": self._default_coefficient(),
            "market_data_tier": self._default_tier(),
        }
        for key, value in values.items():
            existing = db.get(RuntimeSetting, key)
            if not existing:
                db.add(RuntimeSetting(key=key, value_json=value, description=DEFAULT_KEYS[key]))
        db.flush()

    def get_all(self, db: Session) -> dict[str, Any]:
        raw = self._raw_settings(db)
        values = {key: value for key, value in raw.items() if key not in SECRET_KEYS}
        stored_token = raw.get("tushare_token") if isinstance(raw.get("tushare_token"), str) else ""
        token_set = bool((stored_token or "").strip()) or bool(self._env_token())
        tier = values.get("market_data_tier") or self._default_tier()
        values["market_data_tier"] = tier if tier in {"usable", "complete"} else self._default_tier()
        values["tushare_token_set"] = token_set
        values["env_has_tushare_token"] = bool(self._env_token())
        values["complete_ready"] = values["market_data_tier"] == "complete" and token_set
        values["ftshare_enabled"] = bool(self.settings.ftshare_enabled)
        values["ftshare_qualification"] = self.settings.ftshare_qualification
        values["ftshare_ready"] = bool(
            self.settings.ftshare_enabled and self.settings.ftshare_qualification == "qualified"
        )
        probe = raw.get("ftshare_last_probe")
        values["ftshare_last_probe"] = probe if isinstance(probe, dict) else None
        values["active_provider"] = self.resolve_settings(db).market_provider
        return values

    def resolve_settings(self, db: Session, token_override: str | None = None) -> Settings:
        if self.settings.market_provider == "mock":
            return self.settings
        # These modes are complete provider selections, rather than the
        # legacy usable/complete Tushare tier switch.  Preserve them so the
        # factory can enforce FTShare's explicit enablement and ordering.
        if self.settings.market_provider in {"ftshare", "public_composite"}:
            return self.settings
        raw = self._raw_settings(db)
        tier = raw.get("market_data_tier") or self._default_tier()
        token = self._resolve_token(db, token_override)
        if tier == "complete" and token:
            return self.settings.model_copy(update={"market_provider": "composite", "tushare_token": token})
        public_provider = (
            "public_composite"
            if self.settings.ftshare_enabled and self.settings.ftshare_qualification == "qualified"
            else "akshare"
        )
        return self.settings.model_copy(update={"market_provider": public_provider, "tushare_token": token})

    def probe_market(
        self,
        db: Session,
        token_override: str | None = None,
        tier_override: str | None = None,
    ) -> dict[str, Any]:
        raw = self._raw_settings(db)
        tier = tier_override or raw.get("market_data_tier") or self._default_tier()
        if tier not in {"usable", "complete"}:
            raise ValueError("market data tier rejected")
        result = {
            "ok": False,
            "skipped": False,
            "tier": tier,
            "provider": None,
            "bars": 0,
            "probe_code": PROBE_CODE,
            "message": "",
            "failure_class": None,
            "providers": [],
        }
        if self.settings.market_provider == "mock":
            row = {
                "provider": "mock",
                "operation": "probe_market",
                "ok": False,
                "status": "skipped",
                "records": 0,
                "latency": 0.0,
                "failure_class": "demo_mode",
                "qualification": "demo",
            }
            result.update(
                {
                    "skipped": True,
                    "provider": "mock",
                    "message": "当前是演示数据源，未向行情网站探测",
                    "providers": [row],
                }
            )
            self._upsert(db, "ftshare_last_probe", {"tier": tier, "providers": [row]}, "最近行情源探测（脱敏）")
            return result
        token = self._resolve_token(db, token_override)
        candidates: list[tuple[str, Settings | None, str | None]] = []
        if tier == "complete":
            candidates.append(("tushare", self.settings.model_copy(update={"market_provider": "tushare", "tushare_token": token}) if token else None, "credentials_missing" if not token else None))
        candidates.append(("akshare", self.settings.model_copy(update={"market_provider": "akshare", "tushare_token": token}), None))
        if self.settings.ftshare_enabled and self.settings.ftshare_qualification == "qualified":
            candidates.append(("ftshare", self.settings.model_copy(update={"market_provider": "ftshare"}), None))
        else:
            candidates.append(("ftshare", None, "disabled" if not self.settings.ftshare_enabled else "unqualified"))

        end = date.today()
        start = end - timedelta(days=PROBE_LOOKBACK_DAYS)
        for provider_name, probe_settings, skipped_reason in candidates:
            started = time.perf_counter()
            row = {
                "provider": provider_name,
                "operation": "fetch_daily_bars",
                "ok": False,
                "status": "skipped" if skipped_reason else "failed",
                "records": 0,
                "latency": 0.0,
                "failure_class": skipped_reason,
                "qualification": self.settings.ftshare_qualification if provider_name == "ftshare" else "not_applicable",
            }
            if skipped_reason:
                result["providers"].append(row)
                continue
            provider = None
            try:
                provider = create_provider(probe_settings)
                bars = provider.fetch_daily_bars(PROBE_CODE, start, end)
                count = len(bars)
                row.update({"ok": count > 0, "status": "ok" if count else "empty", "records": count, "failure_class": None if count else "empty"})
                result["providers"].append(row)
            except Exception as exc:
                label = type(exc).__name__[:64]
                logger.warning("market probe failed for %s: %s", provider_name, label)
                row.update({"status": "failed", "failure_class": label if label in {"CapabilityUnavailable", "ProviderError", "TimeoutError", "ConnectionError", "ValueError", "RuntimeError"} else "ProviderError"})
                result["providers"].append(row)
            finally:
                if provider is not None:
                    close = getattr(provider, "close", None)
                    if callable(close):
                        try:
                            close()
                        except Exception:
                            pass
            row["latency"] = round((time.perf_counter() - started) * 1000, 2)

        successful = next((row for row in result["providers"] if row["ok"]), None)
        result.update(
            {
                "ok": bool(successful),
                "provider": successful["provider"] if successful else None,
                "bars": successful["records"] if successful else 0,
                "message": "探测成功，已拉到日线" if successful else "未探测到可用日线",
                "failure_class": None if successful else "all_providers_unavailable",
            }
        )
        safe_rows = [
            {key: row.get(key) for key in ("provider", "operation", "ok", "status", "records", "latency", "failure_class", "qualification")}
            for row in result["providers"]
        ]
        self._upsert(db, "ftshare_last_probe", {"tier": tier, "providers": safe_rows}, "最近行情源探测（脱敏）")
        return result

    def update(self, db: Session, updates: dict[str, Any]) -> dict[str, Any]:
        validators = {
            "quote_refresh_minutes": (1, 60),
            "signal_refresh_minutes": (5, 120),
            "news_refresh_minutes": (5, 240),
            "lunch_news_refresh_minutes": (3, 120),
        }
        if updates.get("clear_tushare_token"):
            self._clear_token(db)
        elif "tushare_token" in updates:
            token = self._validated_token(updates["tushare_token"])
            self._upsert(db, "tushare_token", token, TOKEN_DESCRIPTION)

        for key, value in updates.items():
            if key in {"tushare_token", "clear_tushare_token"}:
                continue
            if key == "market_data_tier":
                if value not in {"usable", "complete"}:
                    raise ValueError("market data tier rejected")
                self._upsert(db, key, value, DEFAULT_KEYS[key])
                continue
            if key in FLOAT_KEYS:
                lower, upper = FLOAT_KEYS[key]
                float_value = round(float(value), 2)
                if not lower <= float_value <= upper:
                    raise ValueError(f"{key} 必须在 {lower}-{upper}")
                self._upsert(db, key, float_value, DEFAULT_KEYS[key])
                continue
            if key not in validators:
                continue
            lower, upper = validators[key]
            int_value = int(value)
            if not lower <= int_value <= upper:
                raise ValueError(f"{key} 必须在 {lower}-{upper}")
            self._upsert(db, key, int_value, DEFAULT_KEYS[key])
        db.flush()
        return self.get_all(db)
