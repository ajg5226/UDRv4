"""Regression tests for production configuration safety."""

import json

import pytest

from atlas.core.config import reload_settings
from atlas.core.exceptions import ConfigurationError
from atlas.dashboard import auth
from atlas.storage.database import Database


@pytest.fixture(autouse=True)
def clear_settings_cache():
    reload_settings()
    yield
    reload_settings()


def test_dashboard_auth_fails_closed_without_production_users(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr("atlas.core.secrets.get_secret", lambda name, default=None: None)
    reload_settings()

    with pytest.raises(ConfigurationError, match="Dashboard users are required"):
        auth.get_users()


def test_dashboard_auth_uses_configured_secret_in_production(monkeypatch):
    password_hash = auth.hash_password("correct horse battery staple")
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(
        "atlas.core.secrets.get_secret",
        lambda name, default=None: json.dumps({"admin": password_hash}),
    )
    reload_settings()

    assert auth.verify_password("admin", "correct horse battery staple") is True
    assert auth.verify_password("admin", "wrong") is False


def test_database_fails_closed_without_production_connection(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DB_CONNECTION", raising=False)
    monkeypatch.setattr("atlas.core.secrets.get_secret", lambda name, default=None: None)
    reload_settings()

    with pytest.raises(ConfigurationError, match="Database connection string is required"):
        Database()


def test_database_uses_configured_secret_in_production(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DB_CONNECTION", raising=False)
    monkeypatch.setattr(
        "atlas.core.secrets.get_secret",
        lambda name, default=None: "sqlite:///:memory:",
    )
    reload_settings()

    db = Database()

    assert db._connection_string == "sqlite:///:memory:"
