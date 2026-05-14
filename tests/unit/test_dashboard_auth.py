"""Regression tests for dashboard credential loading."""

import hashlib

from atlas.core import config, secrets
from atlas.dashboard import auth


def _reset_settings() -> None:
    config.get_settings.cache_clear()
    secrets._manager = None


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def test_production_without_configured_users_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)
    _reset_settings()

    assert auth.get_users() == {}
    assert auth.verify_password("admin", "atlas123") is False


def test_malformed_configured_users_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "{not-json")
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)
    _reset_settings()

    assert auth.get_users() == {}
    assert auth.verify_password("admin", "atlas123") is False


def test_configured_users_are_loaded_from_secret_name(monkeypatch) -> None:
    password_hash = _hash_password("correct horse battery staple")
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", f'{{"operator": "{password_hash}"}}')
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)
    _reset_settings()

    assert auth.get_users() == {"operator": password_hash}
    assert auth.verify_password("operator", "correct horse battery staple") is True
    assert auth.verify_password("admin", "atlas123") is False


def test_development_without_configured_users_keeps_local_defaults(monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "development")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)
    _reset_settings()

    assert auth.verify_password("admin", "atlas123") is True
