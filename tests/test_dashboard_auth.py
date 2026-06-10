import json

import pytest

from atlas.core.config import get_settings
from atlas.core.exceptions import ConfigurationError
from atlas.dashboard import auth


@pytest.fixture(autouse=True)
def clear_auth_environment(monkeypatch: pytest.MonkeyPatch):
    """Keep cached settings and auth-related environment isolated per test."""
    monkeypatch.delenv("ATLAS_ENV", raising=False)
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.delenv("ATLAS_DASHBOARD__AUTH__ENABLED", raising=False)
    monkeypatch.setattr(auth, "get_secret", lambda name: None)
    get_settings.cache_clear()

    yield

    get_settings.cache_clear()


def test_production_requires_configured_dashboard_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError, match="Dashboard users must be configured"):
        auth.get_users()


def test_production_rejects_malformed_dashboard_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "{not-json")
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError, match="Invalid dashboard user credentials JSON"):
        auth.get_users()


def test_production_loads_dashboard_users_from_configured_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    password_hash = auth.hash_password("safe-password")
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setattr(
        auth,
        "get_secret",
        lambda name: json.dumps({"operator": password_hash})
        if name == "atlas-dashboard-users"
        else None,
    )
    get_settings.cache_clear()

    assert auth.verify_password("operator", "safe-password")
    assert not auth.verify_password("admin", "atlas123")


def test_development_keeps_default_dashboard_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "development")
    get_settings.cache_clear()

    assert auth.verify_password("admin", "atlas123")
    assert auth.verify_password("analyst", "atlas123")


def test_production_rejects_disabled_dashboard_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD__AUTH__ENABLED", "false")
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError, match="cannot be disabled"):
        auth.dashboard_auth_enabled()


def test_development_allows_disabled_dashboard_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "development")
    monkeypatch.setenv("ATLAS_DASHBOARD__AUTH__ENABLED", "false")
    get_settings.cache_clear()

    assert auth.dashboard_auth_enabled() is False
