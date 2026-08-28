from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", PROJECT_ROOT / "deploy" / ".env.production"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "中国 ETF/LOF 私有决策看板"
    app_env: Literal["development", "test", "production"] = "development"
    app_version: str = "0.4.0"
    timezone_name: str = Field(default="Asia/Shanghai", alias="TZ")

    database_url: str = "sqlite:///./fund_decision.sqlite3"
    auto_create_schema: bool = True
    sql_echo: bool = False

    auth_enabled: bool = True
    private_access_token: str = "change-this-private-token-at-least-32-chars"
    trusted_proxy_headers: bool = False

    market_provider: Literal["mock", "tushare", "akshare", "composite"] = "mock"
    allow_mock_fallback: bool = False
    tushare_token: str = ""
    tushare_realtime_candidates: str = "rt_etf_k,realtime_quote,rt_k"
    akshare_timeout_seconds: float = 25.0
    news_rss_urls: str = ""
    news_rss_timeout_seconds: float = 20.0

    watchlist_path: Path = PROJECT_ROOT / "config" / "watchlist.json"
    strategy_path: Path = PROJECT_ROOT / "config" / "strategy.json"
    taxonomy_path: Path = PROJECT_ROOT / "config" / "sector_taxonomy.json"
    reports_dir: Path = PROJECT_ROOT / "reports"

    quote_refresh_minutes: int = 3
    signal_refresh_minutes: int = 15
    news_refresh_minutes: int = 30
    lunch_news_refresh_minutes: int = 10
    scheduler_tick_seconds: int = 30
    scheduler_enabled: bool = True

    llm_enabled: bool = False
    llm_api_base: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = ""
    llm_api_mode: Literal["chat_completions", "responses"] = "chat_completions"
    llm_timeout_seconds: float = 50.0
    llm_max_input_chars: int = 12000

    cors_origins: str = ""
    log_level: str = "INFO"

    @field_validator("private_access_token")
    @classmethod
    def validate_token(cls, value: str) -> str:
        if value and len(value) < 16:
            raise ValueError("PRIVATE_ACCESS_TOKEN 至少 16 个字符；生产环境建议 32 个以上")
        return value

    @field_validator("quote_refresh_minutes")
    @classmethod
    def validate_quote_interval(cls, value: int) -> int:
        if not 1 <= value <= 60:
            raise ValueError("QUOTE_REFRESH_MINUTES 必须在 1-60")
        return value

    @field_validator("signal_refresh_minutes")
    @classmethod
    def validate_signal_interval(cls, value: int) -> int:
        if not 5 <= value <= 120:
            raise ValueError("SIGNAL_REFRESH_MINUTES 必须在 5-120")
        return value


    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.app_env == "production":
            unsafe_tokens = {
                "change-this-private-token-at-least-32-chars",
                "CHANGE_ME_AT_LEAST_32_RANDOM_CHARS",
                "",
            }
            if self.auth_enabled and self.private_access_token in unsafe_tokens:
                raise ValueError("生产环境必须配置随机 PRIVATE_ACCESS_TOKEN")
            if self.llm_enabled and not (self.llm_api_key and self.llm_model):
                raise ValueError("LLM_ENABLED=true 时必须配置 LLM_API_KEY 与 LLM_MODEL")
        return self

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def news_rss_url_list(self) -> list[str]:
        normalized = self.news_rss_urls.replace("\n", ",").replace(";", ",")
        return [item.strip() for item in normalized.split(",") if item.strip()]

    def load_strategy(self) -> dict:
        data = json.loads(self.strategy_path.read_text(encoding="utf-8"))
        intervals = data.setdefault("intervals", {})
        intervals["quote_minutes"] = self.quote_refresh_minutes
        intervals["signal_minutes"] = self.signal_refresh_minutes
        intervals["news_minutes"] = self.news_refresh_minutes
        intervals["lunch_news_minutes"] = self.lunch_news_refresh_minutes
        return data

    def load_watchlist(self) -> dict:
        return json.loads(self.watchlist_path.read_text(encoding="utf-8"))

    def load_taxonomy(self) -> dict:
        return json.loads(self.taxonomy_path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
