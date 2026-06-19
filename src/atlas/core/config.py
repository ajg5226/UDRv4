"""Configuration management for ATLAS."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def find_project_root() -> Path:
    """Find the project root directory."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


PROJECT_ROOT = find_project_root()
CONFIG_DIR = PROJECT_ROOT / "config"
DEVELOPMENT_ENVIRONMENTS = {"development", "dev", "local", "test", "testing"}


def is_development_environment(environment: Optional[str] = None) -> bool:
    """Return True when local fallback behavior is safe."""
    env = environment or os.getenv("ATLAS_ENV", "development")
    return env.strip().lower() in DEVELOPMENT_ENVIRONMENTS


class RetryConfig(BaseModel):
    """Retry configuration."""

    max_attempts: int = 3
    backoff_seconds: list[int] = Field(default_factory=lambda: [60, 300, 900])


class PipelineConfig(BaseModel):
    """Pipeline execution configuration."""

    schedule: str = "0 5 * * *"
    timezone: str = "America/New_York"
    completion_target_hour: int = 6
    retry: RetryConfig = Field(default_factory=RetryConfig)
    parallel_providers: bool = True
    max_parallel_workers: int = 4
    batch_size_days: int = 30
    default_providers: list[str] = Field(default_factory=lambda: ["tiingo", "fred"])


class DatabaseConfig(BaseModel):
    """Database configuration."""

    driver: str = "mssql+pyodbc"
    connection_string_key: str = "atlas-db-connection"
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    pool_recycle: int = 3600
    query_timeout: int = 300


class RawArchiveConfig(BaseModel):
    """Raw data archive configuration."""

    enabled: bool = True
    container: str = "atlas-raw"
    retention_days: int = 365


class StorageConfig(BaseModel):
    """Storage configuration."""

    raw_archive: RawArchiveConfig = Field(default_factory=RawArchiveConfig)
    connection_string_key: str = "atlas-storage-connection"


class ProviderConfig(BaseModel):
    """Base provider configuration."""

    enabled: bool = True
    api_key_secret: str
    base_url: str
    timeout_seconds: int = 60


class TiingoConfig(ProviderConfig):
    """Tiingo provider configuration."""

    api_key_secret: str = "tiingo-api-key"
    base_url: str = "https://api.tiingo.com"
    rate_limit_per_hour: int = 500
    include_adjusted: bool = True
    start_date: str = "2005-01-01"


class FredConfig(ProviderConfig):
    """FRED provider configuration."""

    api_key_secret: str = "fred-api-key"
    base_url: str = "https://api.stlouisfed.org/fred"
    rate_limit_per_minute: int = 120
    series_config: str = "config/providers/fred_series.yaml"


class ProvidersConfig(BaseModel):
    """All providers configuration."""

    tiingo: TiingoConfig = Field(default_factory=TiingoConfig)
    fred: FredConfig = Field(default_factory=FredConfig)


class FeaturesConfig(BaseModel):
    """Feature engine configuration."""

    enabled: bool = True
    registry_config: str = "config/features/registry.yaml"
    parallel_calculation: bool = True
    max_lookback_days: int = 252


class InstrumentsConfig(BaseModel):
    """Instruments configuration."""

    universe_source: str = "provider"  # "provider", "csv", "database"
    universe_csv: str = "config/instruments/universe.csv"
    tags_config: str = "config/instruments/tags.yaml"


class AppInsightsConfig(BaseModel):
    """Application Insights configuration."""

    enabled: bool = True
    connection_string_key: str = "appinsights-connection"


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = "INFO"
    format: str = "json"
    app_insights: AppInsightsConfig = Field(default_factory=AppInsightsConfig)

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v = v.upper()
        if v not in valid_levels:
            raise ValueError(f"Invalid log level: {v}")
        return v


class EmailChannelConfig(BaseModel):
    """Email notification channel configuration."""

    enabled: bool = True
    recipients_secret: str = "atlas-alert-emails"


class NotificationChannelsConfig(BaseModel):
    """Notification channels configuration."""

    email: EmailChannelConfig = Field(default_factory=EmailChannelConfig)


class NotificationsConfig(BaseModel):
    """Notifications configuration."""

    on_failure: bool = True
    on_partial_success: bool = True
    on_anomaly: bool = True
    channels: NotificationChannelsConfig = Field(default_factory=NotificationChannelsConfig)


class DashboardAuthConfig(BaseModel):
    """Dashboard authentication configuration."""

    enabled: bool = True
    method: str = "simple"  # "simple" or "azure_ad"
    users_secret: str = "atlas-dashboard-users"
    session_secret: str = "atlas-session-secret"


class DashboardConfig(BaseModel):
    """Dashboard configuration."""

    auth: DashboardAuthConfig = Field(default_factory=DashboardAuthConfig)
    page_title: str = "ATLAS Dashboard"
    theme: str = "light"
    default_lookback_days: int = 30
    max_export_rows: int = 100000


class KeyVaultConfig(BaseModel):
    """Azure Key Vault configuration."""

    vault_url_env: str = "ATLAS_KEYVAULT_URL"


class Settings(BaseSettings):
    """Main settings class combining all configuration."""

    model_config = SettingsConfigDict(
        env_prefix="ATLAS_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # Environment
    environment: str = Field(default="development", alias="ATLAS_ENV")

    # Components
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    features: FeaturesConfig = Field(default_factory=FeaturesConfig)
    instruments: InstrumentsConfig = Field(default_factory=InstrumentsConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    keyvault: KeyVaultConfig = Field(default_factory=KeyVaultConfig)

    @classmethod
    def from_yaml(cls, config_path: Optional[Path] = None) -> "Settings":
        """Load settings from YAML file(s)."""
        if config_path is None:
            config_path = CONFIG_DIR / "default.yaml"

        config_data: dict[str, Any] = {}

        # Load base config
        if config_path.exists():
            with open(config_path) as f:
                config_data = yaml.safe_load(f) or {}

        # Load environment-specific overrides
        env = os.getenv("ATLAS_ENV", "development")
        env_config_path = CONFIG_DIR / "environments" / f"{env}.yaml"
        if env_config_path.exists():
            with open(env_config_path) as f:
                env_config = yaml.safe_load(f) or {}
                config_data = deep_merge(config_data, env_config)

        return cls(**config_data)


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dictionaries."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings.from_yaml()


def reload_settings() -> Settings:
    """Reload settings (clears cache)."""
    get_settings.cache_clear()
    return get_settings()
