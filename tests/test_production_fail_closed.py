"""Regression tests for production fail-closed safeguards."""

import hashlib
from types import SimpleNamespace

import pytest

from atlas.core.config import get_settings
from atlas.core.exceptions import ConfigurationError
from atlas.dashboard import auth
from atlas.storage.database import Database


@pytest.fixture(autouse=True)
def clear_config_cache(monkeypatch: pytest.MonkeyPatch):
    """Keep environment-backed settings isolated between tests."""
    monkeypatch.delenv("ATLAS_DB_CONNECTION", raising=False)
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_dashboard_users_require_configured_secret_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")

    with pytest.raises(ConfigurationError, match="Dashboard users secret is required"):
        auth.get_users()


def test_dashboard_users_reject_malformed_secret_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", '{"admin": "plain-text-password"}')

    with pytest.raises(ConfigurationError, match="SHA-256 password hashes"):
        auth.get_users()


def test_dashboard_users_load_configured_secret_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    password_hash = hashlib.sha256(b"safe-password").hexdigest()
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", f'{{"admin": "{password_hash}"}}')

    assert auth.verify_password("admin", "safe-password")
    assert not auth.verify_password("admin", "wrong-password")


def test_dashboard_development_defaults_remain_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "development")

    assert auth.verify_password("admin", "atlas123")


def test_dashboard_auth_cannot_be_disabled_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = SimpleNamespace(
        environment="production",
        dashboard=SimpleNamespace(auth=SimpleNamespace(enabled=False)),
    )
    monkeypatch.setattr(auth, "get_settings", lambda: settings)

    with pytest.raises(ConfigurationError, match="cannot be disabled"):
        auth.validate_auth_configuration()


def test_database_requires_connection_string_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")

    with pytest.raises(ConfigurationError, match="Database connection string is required"):
        Database()


def test_database_development_sqlite_fallback_remains_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "development")

    db = Database()

    assert db._connection_string == "sqlite:///atlas_dev.db"
