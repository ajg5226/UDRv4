"""Regression tests for database connection-string configuration."""

import pytest

from atlas.core.config import get_settings
from atlas.core.exceptions import ConfigurationError
from atlas.storage.database import Database, reset_database


@pytest.fixture(autouse=True)
def reset_db_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ATLAS_DB_CONNECTION", raising=False)
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)
    reset_database()
    get_settings.cache_clear()
    yield
    reset_database()
    get_settings.cache_clear()


def test_development_falls_back_to_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "development")
    monkeypatch.setattr("atlas.core.secrets.get_secret", lambda name: None)
    get_settings.cache_clear()

    assert Database()._connection_string == "sqlite:///atlas_dev.db"


def test_production_requires_database_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setattr("atlas.core.secrets.get_secret", lambda name: None)
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError):
        Database()


def test_production_uses_database_connection_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setattr(
        "atlas.core.secrets.get_secret",
        lambda name: "sqlite:///:memory:",
    )
    get_settings.cache_clear()

    assert Database()._connection_string == "sqlite:///:memory:"
