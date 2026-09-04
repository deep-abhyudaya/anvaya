"""ANVAYA configuration — environment-driven settings."""

from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    database_url: str = "sqlite:///./anvaya.db"
    better_auth_secret: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    nvidia_api_key: str = ""
    nvidia_model: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_timeout_ms: int = 15000
    nvidia_max_retries: int = 2
    nvidia_rate_limit_rpm: int = 40
    lyzr_api_key: str = ""
    lyzr_base_url: str = ""
    openrouter_api_key: str = ""
    openrouter_model: str = ""
    openrouter_timeout_ms: int = 30000
    opencode_api_key: str = ""
    opencode_model: str = ""
    opencode_base_url: str = "https://opencode.ai/zen/v1"
    opencode_timeout_ms: int = 30000
    opencode_rate_limit_rpm: int = 60
    seekai_api_key: str = ""
    seekai_base_url: str = "https://seekai.cc/v1"
    seekai_model: str = ""
    seekai_timeout_ms: int = 30000
    seekai_rate_limit_rpm: int = 60
    gmicloud_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("GMICLOUD_API_KEY", "GMI_API_KEY"),
    )
    gmicloud_base_url: str = Field(
        default="https://api.gmi-serving.com/v1",
        validation_alias=AliasChoices("GMICLOUD_BASE_URL", "GMI_BASE_URL"),
    )
    gmicloud_model: str = Field(
        default="",
        validation_alias=AliasChoices("GMICLOUD_MODEL", "GMI_MODEL"),
    )
    gmicloud_free_only: bool = Field(
        default=False,
        validation_alias=AliasChoices("GMICLOUD_FREE_ONLY", "GMI_FREE_ONLY"),
    )
    gmicloud_timeout_ms: int = 30000
    gmicloud_rate_limit_rpm: int = 60
    empero_api_key: str = ""
    empero_base_url: str = "https://free.empero.org/v1"
    empero_model: str = ""
    empero_timeout_ms: int = 30000
    empero_rate_limit_rpm: int = 60
    agentrouter_api_key: str = ""
    agentrouter_model: str = ""
    agentrouter_timeout_ms: int = 30000
    agentrouter_max_retries: int = 2
    agentrouter_rate_limit_rpm: int = 40
    tavily_api_key: str = ""
    n8n_webhook_url: str = ""
    gmail_credentials_path: str = ""
    gmail_from_email: str = ""
    swytchcode_api_key: str = ""
    swytchcode_base_url: str = ""

    startuped_api_key: str = ""
    startuped_base_url: str = "https://www.startuped.ai"
    startuped_signals_enabled: bool = True
    startuped_client_header: str = "sdk-python"
    startuped_timeout_seconds: float = 2.0
    startuped_queue_size: int = 1000
    startuped_allow_local_config: bool = True
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = True
    log_level: str = "info"
    cli_log_level: str = "error"

    uploadthing_secret: str = ""
    uploadthing_app_id: str = ""

    base_dir: Path = Path(__file__).resolve().parent.parent.parent
    artifacts_dir: Path = Path(__file__).resolve().parent.parent.parent / "ml" / "artifacts"
    datasets_dir: Path = Path(__file__).resolve().parent.parent.parent / "datasets"

    isolation_forest_n_estimators: int = 100
    isolation_forest_contamination: float = 0.05
    detection_threshold: float = -0.5

    max_repair_iterations: int = 3

    poll_interval_seconds: int = 4

    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ]

    class Config:
        env_file = [str(_PROJECT_ROOT / ".env"), str(_PROJECT_ROOT / ".env.local")]
        env_file_encoding = "utf-8"

    @model_validator(mode="after")
    def _resolve_sqlite_database_url(self) -> "Settings":
        """Resolve relative SQLite paths against the project root."""
        if not self.database_url.startswith("sqlite:///"):
            return self
        raw_path = self.database_url[len("sqlite:///") :]
        if raw_path in (":memory:", "", "/dev/null"):
            return self
        if not Path(raw_path).is_absolute():
            self.database_url = f"sqlite:///{(self.base_dir / raw_path).resolve()}"
        return self

    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def is_llm_enabled(self) -> bool:
        return bool(
            self.openai_api_key
            or self.nvidia_api_key
            or self.lyzr_api_key
            or self.openrouter_api_key
            or self.opencode_api_key
            or self.agentrouter_api_key
            or self.seekai_api_key
            or self.gmicloud_api_key
            or self.empero_api_key
        )

    def is_agentrouter_enabled(self) -> bool:
        return bool(self.agentrouter_api_key)

    def is_nvidia_enabled(self) -> bool:
        return bool(self.nvidia_api_key and self.nvidia_model)

    def is_lyzr_enabled(self) -> bool:
        return bool(self.lyzr_api_key)

    def is_openrouter_enabled(self) -> bool:
        return bool(self.openrouter_api_key)

    def is_opencode_enabled(self) -> bool:
        return bool(self.opencode_api_key)

    def is_seekai_enabled(self) -> bool:
        return bool(self.seekai_api_key)

    def is_gmicloud_enabled(self) -> bool:
        return bool(self.gmicloud_api_key)

    def is_empero_enabled(self) -> bool:
        return self.empero_api_key != "disabled"

    def is_tavily_enabled(self) -> bool:
        return bool(self.tavily_api_key)

    def is_n8n_enabled(self) -> bool:
        return bool(self.n8n_webhook_url)

    def is_gmail_enabled(self) -> bool:
        return bool(self.gmail_credentials_path and self.gmail_from_email)

    def is_swytchcode_enabled(self) -> bool:
        return bool(self.swytchcode_api_key)


def get_settings() -> Settings:
    return Settings()


settings = get_settings()
