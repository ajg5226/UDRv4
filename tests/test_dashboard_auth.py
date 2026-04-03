"""Tests for dashboard authentication safety behavior."""

import hashlib
from types import SimpleNamespace

import pytest

from atlas.dashboard import auth


def _settings_with_env(environment: str) -> SimpleNamespace:
    return SimpleNamespace(environment=environment)


def test_get_users_uses_dev_defaults_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: _settings_with_env("development"))

    users = auth.get_users()
    expected_hash = hashlib.sha256("atlas123".encode()).hexdigest()

    assert users["admin"] == expected_hash
    assert users["analyst"] == expected_hash


def test_get_users_fails_closed_in_production_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: _settings_with_env("production"))

    with pytest.raises(ValueError, match="must be configured"):
        auth.get_users()


def test_get_users_rejects_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "{not valid json")
    monkeypatch.setattr(auth, "get_settings", lambda: _settings_with_env("production"))

    with pytest.raises(ValueError, match="not valid JSON"):
        auth.get_users()


def test_verify_password_uses_configured_users(monkeypatch: pytest.MonkeyPatch) -> None:
    password_hash = hashlib.sha256("s3cret".encode()).hexdigest()
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", f'{{"alice":"{password_hash}"}}')
    monkeypatch.setattr(auth, "get_settings", lambda: _settings_with_env("production"))

    assert auth.verify_password("alice", "s3cret")
    assert not auth.verify_password("alice", "wrong")


def test_verify_password_returns_false_when_auth_misconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: _settings_with_env("production"))

    assert not auth.verify_password("admin", "atlas123")


def test_get_auth_configuration_error_reports_production_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: _settings_with_env("production"))

    error = auth.get_auth_configuration_error()

    assert error is not None
    assert "must be configured" in error
