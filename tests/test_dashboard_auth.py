"""Regression tests for dashboard authentication behavior."""

import hashlib
import json

from atlas.core.config import reload_settings
from atlas.dashboard.auth import get_users, verify_password


def test_get_users_does_not_fallback_to_default_in_production(monkeypatch) -> None:
    """Production env must not expose hardcoded default credentials."""
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    reload_settings()

    assert get_users() == {}
    assert not verify_password("admin", "atlas123")


def test_get_users_keeps_default_credentials_in_development(monkeypatch) -> None:
    """Development env retains default credentials for local use."""
    monkeypatch.setenv("ATLAS_ENV", "development")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    reload_settings()

    users = get_users()
    assert set(users.keys()) == {"admin", "analyst"}
    assert verify_password("admin", "atlas123")


def test_get_users_uses_configured_users_in_production(monkeypatch) -> None:
    """Configured users should work in production mode."""
    monkeypatch.setenv("ATLAS_ENV", "production")
    password_hash = hashlib.sha256("super-secret".encode()).hexdigest()
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", json.dumps({"alice": password_hash}))
    reload_settings()

    assert get_users() == {"alice": password_hash}
    assert verify_password("alice", "super-secret")
    assert not verify_password("admin", "atlas123")
