import pytest

from atlas.core.config import get_settings
from atlas.core.exceptions import ConfigurationError
from atlas.storage.database import Database


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_database_connection_fails_closed_in_production(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DB_CONNECTION", raising=False)
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)

    with pytest.raises(ConfigurationError):
        Database()


def test_database_uses_local_sqlite_in_development(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "development")
    monkeypatch.delenv("ATLAS_DB_CONNECTION", raising=False)
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)

    db = Database()

    assert db._connection_string == "sqlite:///atlas_dev.db"
