"""Regression tests for dashboard authentication credential loading."""

import hashlib
from types import SimpleNamespace

import pytest

from atlas.dashboard import auth


def _settings(environment: str) -> SimpleNamespace:
    return SimpleNamespace(
        environment=environment,
        dashboard=SimpleNamespace(
            auth=SimpleNamespace(users_secret="atlas-dashboard-users"),
        ),
    )


def test_get_users_fails_closed_in_production_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Production auth must not fall back to known development passwords."""
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr(auth, "get_secret", lambda _: None)

    with pytest.raises(RuntimeError, match="Dashboard credentials are not configured"):
        auth.get_users()


def test_get_users_rejects_malformed_env_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """Malformed env credentials should not silently activate defaults."""
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "{not-valid-json")
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))

    with pytest.raises(ValueError, match="Invalid dashboard users JSON"):
        auth.get_users()


def test_get_users_keeps_development_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Development environment still allows local bootstrap credentials."""
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("development"))
    monkeypatch.setattr(auth, "get_secret", lambda _: None)

    users = auth.get_users()
    assert users["admin"] == hashlib.sha256("atlas123".encode()).hexdigest()
    assert users["analyst"] == hashlib.sha256("atlas123".encode()).hexdigest()
