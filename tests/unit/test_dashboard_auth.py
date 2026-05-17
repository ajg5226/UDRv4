"""Regression tests for dashboard authentication."""

import json
from types import SimpleNamespace

from atlas.dashboard import auth


def _settings(environment: str = "production") -> SimpleNamespace:
    return SimpleNamespace(
        environment=environment,
        dashboard=SimpleNamespace(
            auth=SimpleNamespace(users_secret="atlas-dashboard-users"),
        ),
    )


def _configure_auth(monkeypatch, environment: str, secret_value: str | None) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: _settings(environment))
    monkeypatch.setattr(auth, "get_secret", lambda secret_name: secret_value)


def test_production_without_configured_users_rejects_default_credentials(monkeypatch) -> None:
    _configure_auth(monkeypatch, "production", None)

    assert auth.get_users() == {}
    assert auth.verify_password("admin", "atlas123") is False
    assert auth.verify_password("analyst", "atlas123") is False


def test_production_with_malformed_users_fails_closed(monkeypatch) -> None:
    _configure_auth(monkeypatch, "production", "{not-json")

    assert auth.get_users() == {}
    assert auth.verify_password("admin", "atlas123") is False


def test_production_with_non_mapping_users_fails_closed(monkeypatch) -> None:
    _configure_auth(monkeypatch, "production", json.dumps(["admin"]))

    assert auth.get_users() == {}
    assert auth.verify_password("admin", "atlas123") is False


def test_production_accepts_configured_secret_users(monkeypatch) -> None:
    users = {"operator": auth.hash_password("correct-password")}
    _configure_auth(monkeypatch, "production", json.dumps(users))

    assert auth.verify_password("operator", "correct-password") is True
    assert auth.verify_password("operator", "wrong-password") is False


def test_development_without_configured_users_allows_default_credentials(monkeypatch) -> None:
    _configure_auth(monkeypatch, "development", None)

    assert auth.verify_password("admin", "atlas123") is True
    assert auth.verify_password("analyst", "atlas123") is True
