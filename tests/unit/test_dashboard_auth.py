"""Tests for dashboard authentication behavior."""

from types import SimpleNamespace

import pytest

from atlas.dashboard import auth


def _set_environment(monkeypatch: pytest.MonkeyPatch, environment: str) -> None:
    """Set dashboard environment for tests."""
    monkeypatch.setattr(
        auth,
        "get_settings",
        lambda: SimpleNamespace(environment=environment),
    )


def test_get_users_returns_env_users_when_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configured users should be used as-is."""
    _set_environment(monkeypatch, "production")
    monkeypatch.setenv(
        "ATLAS_DASHBOARD_USERS",
        '{"alice":"hash1","bob":"hash2"}',
    )

    users = auth.get_users()

    assert users == {"alice": "hash1", "bob": "hash2"}


def test_get_users_uses_defaults_in_development(monkeypatch: pytest.MonkeyPatch) -> None:
    """Development should retain convenience defaults."""
    _set_environment(monkeypatch, "development")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)

    users = auth.get_users()

    assert users["admin"] == auth.hash_password("atlas123")
    assert users["analyst"] == auth.hash_password("atlas123")


def test_get_users_fails_closed_in_production_without_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production must not fall back to known default credentials."""
    _set_environment(monkeypatch, "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)

    with pytest.raises(ValueError, match="not configured"):
        auth.get_users()


def test_get_users_fails_closed_in_production_with_invalid_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid production config must fail closed, not bypass auth."""
    _set_environment(monkeypatch, "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "{not-json}")

    with pytest.raises(ValueError, match="misconfigured"):
        auth.get_users()
