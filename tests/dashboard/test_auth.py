"""Tests for dashboard authentication configuration safety."""

import hashlib

from atlas.core.config import get_settings
from atlas.dashboard.auth import get_users


def test_get_users_development_fallback(monkeypatch):
    """Development environments may use default local credentials."""
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setenv("ATLAS_ENV", "development")
    get_settings.cache_clear()

    users = get_users()

    expected_hash = hashlib.sha256("atlas123".encode()).hexdigest()
    assert users["admin"] == expected_hash
    assert users["analyst"] == expected_hash


def test_get_users_production_fails_closed_without_config(monkeypatch):
    """Production must not silently fall back to default credentials."""
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)
    get_settings.cache_clear()

    users = get_users()
    assert users == {}
