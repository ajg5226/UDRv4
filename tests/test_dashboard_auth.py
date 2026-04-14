"""Security-focused tests for dashboard authentication."""

import hashlib
from types import SimpleNamespace

from atlas.dashboard import auth


def test_get_users_uses_defaults_only_in_development(monkeypatch) -> None:
    """Development mode may use local default users for convenience."""
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(environment="development"))

    users = auth.get_users()

    assert users["admin"] == hashlib.sha256("atlas123".encode()).hexdigest()
    assert users["analyst"] == hashlib.sha256("atlas123".encode()).hexdigest()


def test_get_users_fails_closed_for_invalid_json(monkeypatch) -> None:
    """Malformed credential JSON must not fall back to default credentials."""
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", '{"admin": "x"')
    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(environment="production"))

    assert auth.get_users() == {}
    assert auth.verify_password("admin", "atlas123") is False


def test_get_users_fails_closed_in_production_without_credentials(monkeypatch) -> None:
    """Production mode without explicit credentials should deny all logins."""
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(environment="production"))

    assert auth.get_users() == {}
    assert auth.verify_password("admin", "atlas123") is False
