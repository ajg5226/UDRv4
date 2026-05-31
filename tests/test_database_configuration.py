"""Regression tests for database connection configuration."""

import pytest

from atlas.core.config import get_settings
from atlas.core.exceptions import ConfigurationError
from atlas.storage.database import Database


@pytest.fixture(autouse=True)
def clear_settings(monkeypatch):
    monkeypatch.delenv("ATLAS_DB_CONNECTION", raising=False)
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)
    get_settings.cache_clear()

    import atlas.core.secrets as secrets

    secrets._manager = None
    yield
    get_settings.cache_clear()
    secrets._manager = None


def test_production_requires_database_connection(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError, match="Database connection string must be configured"):
        Database()


def test_development_can_fallback_to_local_sqlite(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "development")
    get_settings.cache_clear()

    db = Database()

    assert db._connection_string == "sqlite:///atlas_dev.db"
