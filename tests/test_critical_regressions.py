"""Regression tests for production fail-closed configuration paths."""

import json

import pytest

from atlas.core.config import get_settings
from atlas.core.exceptions import ConfigurationError


def _clear_settings_cache() -> None:
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def clean_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep cached settings and secret managers isolated between tests."""
    monkeypatch.delenv("ATLAS_ENV", raising=False)
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.delenv("ATLAS_DB_CONNECTION", raising=False)
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)
    _clear_settings_cache()
    yield
    _clear_settings_cache()


def test_dashboard_auth_fails_closed_without_production_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production dashboard auth must not fall back to documented defaults."""
    from atlas.dashboard import auth

    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setattr(auth, "get_secret", lambda name: None)
    _clear_settings_cache()

    with pytest.raises(ConfigurationError, match="Dashboard users must be configured"):
        auth.get_users()


def test_dashboard_auth_loads_users_from_configured_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production can use the configured dashboard users Key Vault secret."""
    from atlas.dashboard import auth

    alice_hash = auth.hash_password("correct-horse-battery-staple")
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setattr(
        auth,
        "get_secret",
        lambda name: json.dumps({"alice": alice_hash}),
    )
    _clear_settings_cache()

    assert auth.get_users() == {"alice": alice_hash}
    assert auth.verify_password("alice", "correct-horse-battery-staple")
    assert not auth.verify_password("admin", "atlas123")


def test_dashboard_auth_development_defaults_still_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local development keeps the documented convenience credentials."""
    from atlas.dashboard import auth

    monkeypatch.setenv("ATLAS_ENV", "development")
    monkeypatch.setattr(auth, "get_secret", lambda name: None)
    _clear_settings_cache()

    assert auth.verify_password("admin", "atlas123")
    assert auth.verify_password("analyst", "atlas123")


def test_database_fails_closed_without_production_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production must not silently create a local SQLite database."""
    from atlas.storage.database import Database

    monkeypatch.setenv("ATLAS_ENV", "production")
    _clear_settings_cache()

    with pytest.raises(ConfigurationError, match="Database connection string must be configured"):
        Database()


def test_database_allows_sqlite_fallback_in_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The local SQLite fallback remains available for development."""
    from atlas.storage.database import Database

    monkeypatch.setenv("ATLAS_ENV", "development")
    _clear_settings_cache()

    assert Database()._connection_string == "sqlite:///atlas_dev.db"
