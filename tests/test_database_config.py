"""Regression tests for database connection configuration."""

from collections.abc import Generator

import pytest

from atlas.core.config import get_settings
from atlas.core.exceptions import ConfigurationError
from atlas.storage import database as database_module
from atlas.storage.database import Database


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Generator[None, None, None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_development_can_fall_back_to_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "development")
    monkeypatch.delenv("ATLAS_DB_CONNECTION", raising=False)
    monkeypatch.setattr(database_module, "get_secret", lambda secret_name: None)
    get_settings.cache_clear()

    assert Database()._get_connection_string() == "sqlite:///atlas_dev.db"


def test_production_missing_database_connection_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DB_CONNECTION", raising=False)
    monkeypatch.setattr(database_module, "get_secret", lambda secret_name: None)
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError, match="Database connection string is required"):
        Database()
