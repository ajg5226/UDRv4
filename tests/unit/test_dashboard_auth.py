"""Regression tests for dashboard authentication configuration."""

import json

from atlas.core import secrets
from atlas.core.config import get_settings
from atlas.dashboard import auth


def _reset_settings_and_secrets() -> None:
    get_settings.cache_clear()
    secrets._manager = None


def test_development_allows_default_credentials(monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "development")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)
    _reset_settings_and_secrets()

    assert auth.verify_password("admin", "atlas123") is True


def test_production_without_configured_users_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)
    _reset_settings_and_secrets()

    assert auth.get_users() == {}
    assert auth.verify_password("admin", "atlas123") is False


def test_production_invalid_users_json_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "not-json")
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)
    _reset_settings_and_secrets()

    assert auth.get_users() == {}
    assert auth.verify_password("admin", "atlas123") is False


def test_configured_users_override_development_defaults(monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv(
        "ATLAS_DASHBOARD_USERS",
        json.dumps({"operator": auth.hash_password("strong-password")}),
    )
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)
    _reset_settings_and_secrets()

    assert auth.verify_password("operator", "strong-password") is True
    assert auth.verify_password("admin", "atlas123") is False
