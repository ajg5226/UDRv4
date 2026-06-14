"""Regression tests for dashboard authentication configuration."""

import json
from collections.abc import Generator

import pytest

from atlas.core.config import get_settings
from atlas.core.exceptions import ConfigurationError
from atlas.dashboard import auth


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Generator[None, None, None]:
    """Keep environment-specific settings isolated per test."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_development_defaults_are_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "development")
    monkeypatch.setattr(auth, "get_secret", lambda secret_name: None)
    get_settings.cache_clear()

    assert auth.verify_password("admin", "atlas123") is True


def test_production_missing_users_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setattr(auth, "get_secret", lambda secret_name: None)
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError, match="Dashboard users must be configured"):
        auth.verify_password("admin", "atlas123")


def test_production_malformed_users_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setattr(auth, "get_secret", lambda secret_name: "{not-json")
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError, match="not valid JSON"):
        auth.get_users()


def test_production_configured_users_are_verified(monkeypatch: pytest.MonkeyPatch) -> None:
    password_hash = auth.hash_password("correct-horse-battery-staple")
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setattr(auth, "get_secret", lambda secret_name: json.dumps({"admin": password_hash}))
    get_settings.cache_clear()

    assert auth.verify_password("admin", "correct-horse-battery-staple") is True
    assert auth.verify_password("admin", "atlas123") is False
