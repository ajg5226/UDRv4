"""Regression tests for dashboard authentication configuration."""

import json

import pytest

from atlas.core.config import get_settings
from atlas.core.exceptions import ConfigurationError
from atlas.dashboard.auth import get_users, hash_password, verify_password


def _clear_dashboard_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)
    monkeypatch.delenv("ATLAS_DASHBOARD_AUTH_USERS", raising=False)
    get_settings.cache_clear()


def test_development_uses_default_dashboard_users(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_dashboard_env(monkeypatch)
    monkeypatch.setenv("ATLAS_ENV", "development")
    get_settings.cache_clear()

    assert verify_password("admin", "atlas123")
    assert verify_password("analyst", "atlas123")


def test_configured_dashboard_users_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_dashboard_env(monkeypatch)
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv(
        "ATLAS_DASHBOARD_USERS",
        json.dumps({"ops": hash_password("correct horse battery staple")}),
    )
    get_settings.cache_clear()

    assert verify_password("ops", "correct horse battery staple")
    assert not verify_password("admin", "atlas123")


def test_production_requires_configured_dashboard_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_dashboard_env(monkeypatch)
    monkeypatch.setenv("ATLAS_ENV", "production")
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError, match="Dashboard users are required"):
        get_users()


def test_malformed_dashboard_users_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_dashboard_env(monkeypatch)
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "{not-json")
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError, match="Invalid dashboard users JSON"):
        get_users()
