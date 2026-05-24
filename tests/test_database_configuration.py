"""Regression tests for database connection selection."""

import pytest

from atlas.core.config import get_settings
from atlas.core.exceptions import ConfigurationError
from atlas.storage.database import Database


def _clear_database_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATLAS_DB_CONNECTION", raising=False)
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)
    get_settings.cache_clear()


def test_development_can_fallback_to_local_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_database_env(monkeypatch)
    monkeypatch.setenv("ATLAS_ENV", "development")
    get_settings.cache_clear()

    db = Database()

    assert db._connection_string == "sqlite:///atlas_dev.db"


def test_production_database_configuration_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_database_env(monkeypatch)
    monkeypatch.setenv("ATLAS_ENV", "production")
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError, match="Database connection string is required"):
        Database()
