from __future__ import annotations

import json
import os
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import AliasChoices, Field, FiniteFloat, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.analysis.contracts import AnalysisProvider
from app.market_context.contracts import RegistryConfig

PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ANALYSIS_CONFIG_FIELDS = frozenset(
    {
        "analysis_enabled",
        "analysis_primary_provider",
        "analysis_primary_model",
        "analysis_primary_mode",
        "analysis_prompt_version",
        "analysis_schema_version",
        "analysis_max_input_chars",
        "analysis_codex_enabled",
        "analysis_anthropic_enabled",
        "analysis_deepseek_enabled",
        "openai_api_key",
        "anthropic_api_key",
        "deepseek_api_key",
        "analysis_codex_base_url",
        "analysis_anthropic_base_url",
        "analysis_deepseek_base_url",
        "analysis_codex_timeout_seconds",
        "analysis_anthropic_timeout_seconds",
        "analysis_deepseek_timeout_seconds",
    }
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", PROJECT_ROOT / "deploy" / ".env.production"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    app_name: str = "中国 ETF/LOF 私有决策看板"
    app_env: Literal["development", "test", "production"] = "development"
    app_version: str = "0.6.0"
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
    market_context_path: Path = PROJECT_ROOT / "config" / "market_context.json"
    reports_dir: Path = PROJECT_ROOT / "reports"

    # Portfolio screenshot OCR is local-only by default.  The transient root
    # intentionally lives in the OS private temp area, never under reports.
    ocr_mode: Literal["local_paddle", "disabled", "cloud_review"] = Field(
        default="local_paddle", validation_alias="OCR_MODE"
    )
    ocr_cloud_review_enabled: bool = Field(default=False, validation_alias="OCR_CLOUD_REVIEW_ENABLED")
    ocr_transient_ttl_minutes: int = Field(default=15, validation_alias="OCR_TRANSIENT_TTL_MINUTES", ge=1, le=1440)
    ocr_max_bytes: int = Field(
        default=10 * 1024 * 1024,
        validation_alias=AliasChoices("OCR_MAX_IMAGE_BYTES", "OCR_MAX_BYTES"),
        ge=1024,
        le=50 * 1024 * 1024,
    )
    ocr_max_width: int = Field(default=12_000, validation_alias="OCR_MAX_WIDTH", ge=1, le=50_000)
    ocr_max_height: int = Field(default=12_000, validation_alias="OCR_MAX_HEIGHT", ge=1, le=50_000)
    ocr_max_pixels: int = Field(default=40_000_000, validation_alias="OCR_MAX_PIXELS", ge=1, le=100_000_000)
    ocr_timeout_seconds: FiniteFloat = Field(default=60.0, validation_alias="OCR_TIMEOUT_SECONDS", gt=0, le=300)
    ocr_transient_root: Path = Field(
        default_factory=lambda: Path(tempfile.gettempdir()) / "china-fund-decision" / "ocr-transient",
        validation_alias="OCR_TRANSIENT_ROOT",
    )
    ocr_local_model_dir: Path = Field(
        default=PROJECT_ROOT / "models" / "ocr", validation_alias="OCR_LOCAL_MODEL_DIR"
    )

    quote_refresh_minutes: int = 3
    signal_refresh_minutes: int = 15
    news_refresh_minutes: int = 30
    lunch_news_refresh_minutes: int = 10
    market_context_refresh_minutes: int = 15
    scheduler_tick_seconds: int = 30
    scheduler_enabled: bool = True

    llm_enabled: bool = False
    llm_api_base: str = "https://api.openai.com/v1"
    llm_api_key: str = Field(default="", repr=False, exclude=True)
    llm_model: str = ""
    llm_api_mode: Literal["chat_completions", "responses"] = "chat_completions"
    llm_timeout_seconds: float = 50.0
    llm_max_input_chars: int = 12000

    # Provider-neutral analysis gateway. Keys are SecretStr so settings reprs and
    # validation errors never disclose server-local credentials. ``OPENAI_API_KEY``
    # is the design name for the Codex/OpenAI Responses adapter.
    analysis_enabled: bool = Field(default=False, validation_alias="ANALYSIS_ENABLED")
    analysis_primary_provider: AnalysisProvider | None = Field(
        default=None, validation_alias="ANALYSIS_PRIMARY_PROVIDER"
    )
    analysis_primary_model: str = Field(default="", validation_alias="ANALYSIS_PRIMARY_MODEL", max_length=512)
    analysis_primary_mode: Literal["responses", "messages", "chat_completions"] = Field(
        default="responses", validation_alias="ANALYSIS_PRIMARY_MODE"
    )
    analysis_prompt_version: str = Field(
        default="analysis-v1", validation_alias="ANALYSIS_PROMPT_VERSION", max_length=512
    )
    analysis_schema_version: str = Field(
        default="analysis-v1", validation_alias="ANALYSIS_SCHEMA_VERSION", max_length=512
    )
    analysis_max_input_chars: int = Field(
        default=12000, validation_alias="ANALYSIS_MAX_INPUT_CHARS", gt=0, le=120000
    )

    analysis_codex_enabled: bool = Field(
        default=False, validation_alias=AliasChoices("ANALYSIS_CODEX_ENABLED", "ANALYSIS_OPENAI_ENABLED")
    )
    analysis_anthropic_enabled: bool = Field(default=False, validation_alias="ANALYSIS_ANTHROPIC_ENABLED")
    analysis_deepseek_enabled: bool = Field(default=False, validation_alias="ANALYSIS_DEEPSEEK_ENABLED")
    openai_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices(
            "OPENAI_API_KEY", "ANALYSIS_CODEX_API_KEY", "analysis_codex_api_key"
        ),
        repr=False,
    )
    anthropic_api_key: SecretStr = Field(
        default=SecretStr(""), validation_alias="ANTHROPIC_API_KEY", repr=False
    )
    deepseek_api_key: SecretStr = Field(
        default=SecretStr(""), validation_alias="DEEPSEEK_API_KEY", repr=False
    )
    analysis_codex_base_url: str = Field(
        default="https://api.openai.com/v1",
        validation_alias=AliasChoices("ANALYSIS_CODEX_BASE_URL", "OPENAI_BASE_URL"),
    )
    analysis_anthropic_base_url: str = Field(
        default="https://api.anthropic.com", validation_alias="ANALYSIS_ANTHROPIC_BASE_URL"
    )
    analysis_deepseek_base_url: str = Field(
        default="https://api.deepseek.com", validation_alias="ANALYSIS_DEEPSEEK_BASE_URL"
    )
    analysis_codex_timeout_seconds: FiniteFloat = Field(
        default=50.0,
        validation_alias=AliasChoices("ANALYSIS_CODEX_TIMEOUT_SECONDS", "ANALYSIS_OPENAI_TIMEOUT_SECONDS"),
        gt=0,
        le=300,
    )
    analysis_anthropic_timeout_seconds: FiniteFloat = Field(
        default=50.0, validation_alias="ANALYSIS_ANTHROPIC_TIMEOUT_SECONDS", gt=0, le=300
    )
    analysis_deepseek_timeout_seconds: FiniteFloat = Field(
        default=50.0, validation_alias="ANALYSIS_DEEPSEEK_TIMEOUT_SECONDS", gt=0, le=300
    )

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

    @field_validator("market_context_refresh_minutes")
    @classmethod
    def validate_market_context_interval(cls, value: int) -> int:
        if not 5 <= value <= 1440:
            raise ValueError("MARKET_CONTEXT_REFRESH_MINUTES 必须在 5-1440")
        return value

    @field_validator(
        "analysis_primary_provider",
        "analysis_primary_model",
        "analysis_primary_mode",
        "analysis_prompt_version",
        "analysis_schema_version",
        mode="before",
    )
    @classmethod
    def trim_analysis_identifiers(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


    @model_validator(mode="after")
    def validate_production_secrets(self) -> Settings:
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

    @model_validator(mode="after")
    def validate_ocr_configuration(self) -> Settings:
        if self.ocr_mode == "cloud_review" and not self.ocr_cloud_review_enabled:
            raise ValueError("OCR_MODE=cloud_review requires OCR_CLOUD_REVIEW_ENABLED=true")
        transient = self.ocr_transient_root.resolve()
        reports = self.reports_dir.resolve()
        protected = (
            reports,
            (PROJECT_ROOT / "backend" / "app" / "static").resolve(),
            (PROJECT_ROOT / "backend" / "app").resolve(),
            self.ocr_local_model_dir.resolve(),
        )
        if any(transient == item or transient.is_relative_to(item) or item.is_relative_to(transient) for item in protected):
            raise ValueError("OCR_TRANSIENT_ROOT must be private and separate from reports, source, static, and models")
        if self.ocr_transient_root.is_symlink():
            raise ValueError("OCR_TRANSIENT_ROOT must not be a symlink")
        if transient == Path(transient.anchor):
            raise ValueError("OCR_TRANSIENT_ROOT must not be a filesystem root")
        if self.app_env == "production":
            if os.name == "nt":
                raise ValueError("生产环境 OCR 暂不支持无法可靠验证私有目录 ACL 的 Windows 主机")
            if not self.ocr_transient_root.is_dir():
                raise ValueError("生产环境必须配置已存在的 OCR_TRANSIENT_ROOT")
            # Windows ACL/private-directory validation remains a deployment
            # gate; C2 creates session subdirectories with restrictive ACLs.
            if os.name != "nt":
                mode = self.ocr_transient_root.stat().st_mode
                if mode & 0o077:
                    raise ValueError("生产环境 OCR_TRANSIENT_ROOT 必须是私有 POSIX 目录")
        if self.app_env == "production" and self.ocr_mode == "local_paddle":
            if not self.ocr_local_model_dir.is_dir():
                raise ValueError("生产环境 local_paddle 必须配置已存在的 OCR_LOCAL_MODEL_DIR")
        return self

    @property
    def analysis_codex_api_key(self) -> SecretStr:
        """Compatibility property for the Codex/OpenAI provider-specific name."""
        return self.openai_api_key

    @model_validator(mode="after")
    def validate_analysis_configuration(self) -> Settings:
        """Resolve the one-primary contract and reject ambiguous configurations."""
        explicit_new = self.model_fields_set.intersection(_ANALYSIS_CONFIG_FIELDS)
        legacy_provider = (
            AnalysisProvider.CODEX_OPENAI_RESPONSES
            if self.llm_api_mode == "responses"
            else AnalysisProvider.DEEPSEEK_OPENAI_COMPATIBLE
        )
        if self.llm_enabled and explicit_new:
            raise ValueError("legacy LLM 不得与显式 analysis 配置混用")
        elif self.llm_enabled:
            # One-release bridge for the original LLM_* settings. Responses mode
            # maps to Codex/OpenAI; chat-completions mode maps to the compatible
            # provider. Existing LLM fields remain available to legacy services.
            self.analysis_enabled = True
            if self.analysis_primary_provider is None:
                self.analysis_primary_provider = legacy_provider
            if not self.analysis_primary_model:
                self.analysis_primary_model = self.llm_model.strip()
            if self.analysis_primary_provider == AnalysisProvider.CODEX_OPENAI_RESPONSES:
                if not self.openai_api_key.get_secret_value():
                    self.openai_api_key = SecretStr(self.llm_api_key)
                if self.analysis_codex_base_url == "https://api.openai.com/v1":
                    self.analysis_codex_base_url = self.llm_api_base
                self.analysis_codex_enabled = True
                self.analysis_primary_mode = "responses"
            elif self.analysis_primary_provider == AnalysisProvider.DEEPSEEK_OPENAI_COMPATIBLE:
                if not self.deepseek_api_key.get_secret_value():
                    self.deepseek_api_key = SecretStr(self.llm_api_key)
                if self.analysis_deepseek_base_url == "https://api.deepseek.com":
                    self.analysis_deepseek_base_url = self.llm_api_base
                self.analysis_deepseek_enabled = True
                self.analysis_primary_mode = "chat_completions"

        if not self.analysis_enabled:
            return self

        if self.analysis_primary_provider is None:
            raise ValueError("ANALYSIS_ENABLED=true 时必须配置 ANALYSIS_PRIMARY_PROVIDER")
        enabled = {
            AnalysisProvider.CODEX_OPENAI_RESPONSES: self.analysis_codex_enabled,
            AnalysisProvider.ANTHROPIC_MESSAGES: self.analysis_anthropic_enabled,
            AnalysisProvider.DEEPSEEK_OPENAI_COMPATIBLE: self.analysis_deepseek_enabled,
        }
        explicitly_enabled = [provider for provider, flag in enabled.items() if flag]
        if len(explicitly_enabled) != 1 or explicitly_enabled[0] != self.analysis_primary_provider:
            raise ValueError("分析配置必须且只能启用一个与主 provider 一致的 provider")

        if not self.analysis_primary_model.strip():
            raise ValueError("ANALYSIS_ENABLED=true 时必须配置 ANALYSIS_PRIMARY_MODEL")
        if not self.analysis_prompt_version.strip() or not self.analysis_schema_version.strip():
            raise ValueError("分析配置的 prompt/schema version 不能为空")
        required_key = {
            AnalysisProvider.CODEX_OPENAI_RESPONSES: self.openai_api_key,
            AnalysisProvider.ANTHROPIC_MESSAGES: self.anthropic_api_key,
            AnalysisProvider.DEEPSEEK_OPENAI_COMPATIBLE: self.deepseek_api_key,
        }[self.analysis_primary_provider]
        if not required_key.get_secret_value():
            raise ValueError("分析主 provider 缺少必需的 API key")
        expected_modes = {
            AnalysisProvider.CODEX_OPENAI_RESPONSES: "responses",
            AnalysisProvider.ANTHROPIC_MESSAGES: "messages",
        }
        expected_mode = expected_modes.get(self.analysis_primary_provider)
        if expected_mode is not None and self.analysis_primary_mode != expected_mode:
            raise ValueError("分析主 provider 与 ANALYSIS_PRIMARY_MODE 不一致")
        if self.analysis_primary_provider == AnalysisProvider.DEEPSEEK_OPENAI_COMPATIBLE and self.analysis_primary_mode not in {
            "chat_completions",
            "responses",
        }:
            raise ValueError("DeepSeek 兼容 provider 只支持 chat_completions 或 responses 模式")
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

    def load_market_context(self) -> RegistryConfig:
        return RegistryConfig.model_validate(json.loads(self.market_context_path.read_text(encoding="utf-8")))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
