import pytest

from atlas.core.config import get_settings
from atlas.core.exceptions import DatabaseError
from atlas.storage.database import Database


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_development_database_can_fall_back_to_sqlite(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "development")
    monkeypatch.delenv("ATLAS_DB_CONNECTION", raising=False)
    monkeypatch.setattr("atlas.core.secrets.get_secret", lambda name: None)

    db = Database()

    assert db._connection_string == "sqlite:///atlas_dev.db"


def test_production_database_requires_configured_connection(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DB_CONNECTION", raising=False)
    monkeypatch.setattr("atlas.core.secrets.get_secret", lambda name: None)

    with pytest.raises(DatabaseError, match="Database connection string is not configured"):
        Database()
