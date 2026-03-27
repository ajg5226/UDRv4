"""Regression tests for fail-closed security behavior."""

import hashlib

import pytest

from atlas.core.config import reload_settings
from atlas.core.exceptions import DatabaseError
from atlas.dashboard.auth import get_users, verify_password
from atlas.storage.database import Database


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Ensure settings reflect test-specific environment variables."""
    reload_settings()
    yield
    reload_settings()


def test_dashboard_auth_fails_closed_in_production_when_users_missing(monkeypatch):
    """Production simple auth must reject default fallback credentials."""
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    reload_settings()

    users = get_users()

    assert users == {}
    assert verify_password("admin", "atlas123") is False


def test_dashboard_auth_uses_configured_users_in_production(monkeypatch):
    """Configured production credentials should still authenticate."""
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv(
        "ATLAS_DASHBOARD_USERS",
        '{"admin":"%s"}' % hashlib.sha256("strong-password".encode()).hexdigest(),
    )
    reload_settings()

    assert verify_password("admin", "strong-password") is True
    assert verify_password("admin", "atlas123") is False


def test_database_connection_string_fails_closed_in_production(monkeypatch):
    """Production must not silently write to local SQLite."""
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DB_CONNECTION", raising=False)
    monkeypatch.setattr("atlas.core.secrets.get_secret", lambda *_args, **_kwargs: None)
    reload_settings()

    with pytest.raises(DatabaseError, match="required in production"):
        Database(connection_string=None)


def test_database_connection_string_falls_back_in_development(monkeypatch):
    """Development can still use local SQLite fallback."""
    monkeypatch.setenv("ATLAS_ENV", "development")
    monkeypatch.delenv("ATLAS_DB_CONNECTION", raising=False)
    monkeypatch.setattr("atlas.core.secrets.get_secret", lambda *_args, **_kwargs: None)
    reload_settings()

    db = Database(connection_string=None)
    assert db._connection_string == "sqlite:///atlas_dev.db"
