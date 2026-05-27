"""Regression tests for dashboard authentication configuration."""

import json

import pytest

from atlas.core.config import get_settings
from atlas.core.exceptions import ConfigurationError
from atlas.dashboard import auth


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_development_uses_default_dashboard_users(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "development")
    get_settings.cache_clear()

    assert auth.verify_password("admin", "atlas123")


def test_production_requires_configured_dashboard_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setattr(auth, "get_secret", lambda name: None)
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError):
        auth.get_users()


def test_production_loads_dashboard_users_from_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    password_hash = auth.hash_password("correct-horse-battery-staple")

    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setattr(auth, "get_secret", lambda name: json.dumps({"operator": password_hash}))
    get_settings.cache_clear()

    assert auth.verify_password("operator", "correct-horse-battery-staple")
    assert not auth.verify_password("admin", "atlas123")


def test_malformed_dashboard_users_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "not-json")
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError):
        auth.get_users()
