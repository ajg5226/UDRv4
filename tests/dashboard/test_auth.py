"""Security-focused tests for dashboard authentication."""

import hashlib

from atlas.dashboard.auth import get_users, verify_password


def test_get_users_returns_empty_when_not_configured(monkeypatch) -> None:
    """Auth should fail closed when no credentials are configured."""
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.delenv("ATLAS_DASHBOARD_ALLOW_DEFAULT_USERS", raising=False)

    assert get_users() == {}


def test_get_users_uses_default_credentials_only_with_explicit_opt_in(monkeypatch) -> None:
    """Development defaults require explicit environment opt-in."""
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setenv("ATLAS_DASHBOARD_ALLOW_DEFAULT_USERS", "true")

    users = get_users()
    expected_hash = hashlib.sha256("atlas123".encode()).hexdigest()
    assert users == {"admin": expected_hash, "analyst": expected_hash}


def test_get_users_returns_empty_for_invalid_json(monkeypatch) -> None:
    """Invalid credential payload should disable login, not fallback."""
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "{not-json")
    monkeypatch.delenv("ATLAS_DASHBOARD_ALLOW_DEFAULT_USERS", raising=False)

    assert get_users() == {}


def test_get_users_returns_empty_for_non_object_json(monkeypatch) -> None:
    """Non-object JSON should not be accepted as a user map."""
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", '"oops"')
    monkeypatch.delenv("ATLAS_DASHBOARD_ALLOW_DEFAULT_USERS", raising=False)

    assert get_users() == {}


def test_verify_password_works_with_configured_user_map(monkeypatch) -> None:
    """Password verification succeeds with valid configured users."""
    password = "s3cure"
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", f'{{"operator":"{password_hash}"}}')
    monkeypatch.delenv("ATLAS_DASHBOARD_ALLOW_DEFAULT_USERS", raising=False)

    assert verify_password("operator", password)
    assert not verify_password("operator", "wrong")
    assert not verify_password("missing", password)
