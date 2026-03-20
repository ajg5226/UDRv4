"""Regression tests for dashboard authentication credential loading."""

import json

from atlas.core.config import reload_settings
from atlas.dashboard.auth import get_users, hash_password, verify_password


def _reload_with_env(monkeypatch, env: str, users_json: str | None) -> None:
    """Helper to reset settings cache after environment changes."""
    monkeypatch.setenv("ATLAS_ENV", env)
    if users_json is None:
        monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    else:
        monkeypatch.setenv("ATLAS_DASHBOARD_USERS", users_json)
    reload_settings()


def test_development_uses_default_credentials(monkeypatch) -> None:
    _reload_with_env(monkeypatch, "development", None)

    users = get_users()

    assert "admin" in users
    assert verify_password("admin", "atlas123")


def test_production_fails_closed_without_users_config(monkeypatch) -> None:
    _reload_with_env(monkeypatch, "production", None)

    assert get_users() == {}
    assert not verify_password("admin", "atlas123")


def test_production_uses_configured_users(monkeypatch) -> None:
    users_json = json.dumps({"ops": hash_password("super-secret")})
    _reload_with_env(monkeypatch, "production", users_json)

    assert verify_password("ops", "super-secret")
    assert not verify_password("ops", "wrong")
