from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkspaceSettings(BaseSettings):
    """Independent rollout and resource controls. No model credentials here."""

    model_config = SettingsConfigDict(env_prefix="WORKSPACE_", extra="ignore")
    ui_enabled: bool = False
    daily_review_enabled: bool = False
    bridge_enabled: bool = False
    read_limit: int = Field(default=500, ge=20, le=2000)
    chart_history_limit: int = Field(default=8000, ge=250, le=20000)
    job_ttl_hours: int = Field(default=48, ge=1, le=168)
    job_lease_minutes: int = Field(default=30, ge=1, le=120)
    max_active_jobs: int = Field(default=8, ge=1, le=30)
    daily_job_budget: int = Field(default=30, ge=1, le=200)
    import_max_bytes: int = Field(default=2_000_000, ge=1024, le=5_000_000)
    import_max_rows: int = Field(default=200, ge=1, le=500)
    worker_poll_seconds: int = Field(default=10, ge=2, le=120)


def workspace_settings() -> WorkspaceSettings:
    # Do not cache across tests or a deliberate environment-controlled rollout.
    return WorkspaceSettings()
