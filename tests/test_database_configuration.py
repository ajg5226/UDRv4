from types import SimpleNamespace

import pytest

from atlas.core.exceptions import ConfigurationError
from atlas.storage import database


def _settings(environment: str) -> SimpleNamespace:
    return SimpleNamespace(
        environment=environment,
        database=SimpleNamespace(connection_string_key="atlas-db-connection"),
    )


def test_production_database_requires_configured_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ATLAS_DB_CONNECTION", raising=False)
    monkeypatch.setattr(database, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr(database, "get_secret", lambda name: None)

    with pytest.raises(ConfigurationError):
        database.Database()._get_connection_string()


def test_development_database_keeps_sqlite_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ATLAS_DB_CONNECTION", raising=False)
    monkeypatch.setattr(database, "get_settings", lambda: _settings("development"))
    monkeypatch.setattr(database, "get_secret", lambda name: None)

    assert database.Database()._get_connection_string() == "sqlite:///atlas_dev.db"
