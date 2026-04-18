"""Unit tests for dashboard authentication behavior."""

import hashlib
import json
from types import SimpleNamespace

from atlas.dashboard import auth


def _settings(environment: str, users_secret: str = "atlas-dashboard-users") -> SimpleNamespace:
    """Build a minimal settings object used by auth helpers."""
    return SimpleNamespace(
        environment=environment,
        dashboard=SimpleNamespace(
            auth=SimpleNamespace(users_secret=users_secret),
        ),
    )


def test_get_users_development_fallback_defaults(monkeypatch) -> None:
    """Development mode should still provide default credentials."""
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("development"))
    monkeypatch.setattr(auth, "get_secret", lambda _: None)

    users = auth.get_users()
    expected_hash = hashlib.sha256("atlas123".encode()).hexdigest()

    assert users == {
        "admin": expected_hash,
        "analyst": expected_hash,
    }


def test_get_users_production_fails_closed_when_unconfigured(monkeypatch) -> None:
    """Production mode must not fall back to development credentials."""
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr(auth, "get_secret", lambda _: None)

    assert auth.get_users() == {}


def test_get_users_prefers_valid_env_mapping(monkeypatch) -> None:
    """Environment users JSON should be consumed when valid."""
    env_users = {"ops": "hash-1"}
    secret_call_count = 0

    def fake_get_secret(_: str) -> str:
        nonlocal secret_call_count
        secret_call_count += 1
        return json.dumps({"secret-user": "hash-2"})

    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", json.dumps(env_users))
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr(auth, "get_secret", fake_get_secret)

    assert auth.get_users() == env_users
    assert secret_call_count == 0


def test_get_users_uses_secret_when_env_missing(monkeypatch) -> None:
    """Secret-backed users should be accepted in production."""
    secret_users = {"service": "hash-3"}

    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr(auth, "get_secret", lambda _: json.dumps(secret_users))

    assert auth.get_users() == secret_users


def test_get_users_rejects_invalid_env_json_in_production(monkeypatch) -> None:
    """Invalid users JSON should not unlock access in production."""
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "{not-valid")
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr(auth, "get_secret", lambda _: None)

    assert auth.get_users() == {}
