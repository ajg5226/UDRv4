"""Regression tests for production configuration fail-closed behavior."""

import json

import pytest

from atlas.core.config import get_settings
from atlas.core.exceptions import ConfigurationError


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_dashboard_users_load_from_secret_in_production(monkeypatch):
    from atlas.dashboard import auth

    expected_users = {"ops": auth.hash_password("safe-password")}
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(
        auth,
        "get_secret",
        lambda name: json.dumps(expected_users) if name == "atlas-dashboard-users" else None,
    )

    assert auth.get_users() == expected_users


def test_dashboard_users_reject_malformed_env_in_production(monkeypatch):
    from atlas.dashboard import auth

    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "{not-json")

    with pytest.raises(ConfigurationError, match="valid JSON"):
        auth.get_users()


def test_dashboard_users_missing_in_production_fails_closed(monkeypatch):
    from atlas.dashboard import auth

    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_secret", lambda name: None)

    with pytest.raises(ConfigurationError, match="Dashboard users must be configured"):
        auth.get_users()


def test_dashboard_users_development_defaults_remain_available(monkeypatch):
    from atlas.dashboard import auth

    monkeypatch.setenv("ATLAS_ENV", "development")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_secret", lambda name: None)

    users = auth.get_users()

    assert auth.hash_password("atlas123") == users["admin"]
    assert auth.hash_password("atlas123") == users["analyst"]


def test_database_connection_missing_in_production_fails_closed(monkeypatch):
    from atlas.storage import database

    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DB_CONNECTION", raising=False)
    monkeypatch.setattr("atlas.core.secrets.get_secret", lambda name: None)

    with pytest.raises(ConfigurationError, match="Database connection string is required"):
        database.Database()


def test_database_development_falls_back_to_sqlite(monkeypatch):
    from atlas.storage import database

    monkeypatch.setenv("ATLAS_ENV", "development")
    monkeypatch.delenv("ATLAS_DB_CONNECTION", raising=False)
    monkeypatch.setattr("atlas.core.secrets.get_secret", lambda name: None)

    db = database.Database()

    assert db._connection_string == "sqlite:///atlas_dev.db"
