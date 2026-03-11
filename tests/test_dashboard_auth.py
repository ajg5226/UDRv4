"""Security tests for dashboard authentication defaults."""

import hashlib

from atlas.dashboard.auth import get_users, verify_password


def test_auth_fails_closed_without_user_configuration(monkeypatch) -> None:
    """Missing auth config should not allow any login."""
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.delenv("ATLAS_ALLOW_INSECURE_DASHBOARD_DEFAULTS", raising=False)

    assert get_users() == {}
    assert not verify_password("admin", "atlas123")


def test_invalid_dashboard_users_json_fails_closed(monkeypatch) -> None:
    """Malformed user JSON should disable login instead of falling back."""
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "{not-json}")
    monkeypatch.delenv("ATLAS_ALLOW_INSECURE_DASHBOARD_DEFAULTS", raising=False)

    assert get_users() == {}
    assert not verify_password("admin", "atlas123")


def test_explicit_insecure_defaults_opt_in(monkeypatch) -> None:
    """Insecure local defaults are available only when explicitly enabled."""
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setenv("ATLAS_ALLOW_INSECURE_DASHBOARD_DEFAULTS", "true")

    users = get_users()
    expected_hash = hashlib.sha256(b"atlas123").hexdigest()

    assert users == {"admin": expected_hash, "analyst": expected_hash}
    assert verify_password("admin", "atlas123")


def test_explicit_users_override_insecure_defaults(monkeypatch) -> None:
    """Configured users should take precedence over insecure defaults."""
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", '{"prod_user":"abc123"}')
    monkeypatch.setenv("ATLAS_ALLOW_INSECURE_DASHBOARD_DEFAULTS", "true")

    assert get_users() == {"prod_user": "abc123"}
    assert not verify_password("admin", "atlas123")
