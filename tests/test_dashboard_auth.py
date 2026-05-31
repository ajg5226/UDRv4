"""Regression tests for dashboard authentication configuration."""

import pytest

from atlas.core.config import get_settings
from atlas.core.exceptions import ConfigurationError
from atlas.dashboard.auth import get_users, hash_password, verify_password


@pytest.fixture(autouse=True)
def clear_settings(monkeypatch):
    """Keep settings/env cache state isolated between auth tests."""
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.delenv("ATLAS_DASHBOARD__AUTH__USERS_SECRET", raising=False)
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)
    get_settings.cache_clear()

    import atlas.core.secrets as secrets

    secrets._manager = None
    yield
    get_settings.cache_clear()
    secrets._manager = None


def test_production_requires_configured_dashboard_users(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError, match="Dashboard users must be configured"):
        get_users()


def test_production_rejects_malformed_dashboard_users(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", '{"admin": "unterminated"')
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError, match="Invalid dashboard users JSON"):
        get_users()


def test_production_uses_configured_dashboard_users(monkeypatch):
    password_hash = hash_password("correct horse battery staple")
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", f'{{"admin": "{password_hash}"}}')
    get_settings.cache_clear()

    assert verify_password("admin", "correct horse battery staple")
    assert not verify_password("admin", "atlas123")


def test_development_allows_default_dashboard_users(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "development")
    get_settings.cache_clear()

    assert verify_password("admin", "atlas123")
