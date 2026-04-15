import hashlib
import json
from types import SimpleNamespace

from atlas.dashboard import auth


def _settings(environment: str) -> SimpleNamespace:
    return SimpleNamespace(
        environment=environment,
        dashboard=SimpleNamespace(
            auth=SimpleNamespace(users_secret="atlas-dashboard-users"),
        ),
    )


def test_production_without_configured_users_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr("atlas.core.secrets.get_secret", lambda *_: None)
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)

    assert auth.get_users() == {}
    assert auth.verify_password("admin", "atlas123") is False


def test_development_allows_local_default_users(monkeypatch) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("development"))
    monkeypatch.setattr("atlas.core.secrets.get_secret", lambda *_: None)
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)

    users = auth.get_users()
    assert "admin" in users
    assert auth.verify_password("admin", "atlas123") is True


def test_production_uses_explicit_env_users(monkeypatch) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr("atlas.core.secrets.get_secret", lambda *_: None)
    password_hash = hashlib.sha256("s3cret".encode()).hexdigest()
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", json.dumps({"alice": password_hash}))

    assert auth.verify_password("alice", "s3cret") is True
    assert auth.verify_password("alice", "wrong") is False


def test_invalid_users_json_does_not_enable_defaults_in_production(monkeypatch) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr("atlas.core.secrets.get_secret", lambda *_: None)
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "{invalid-json")

    assert auth.get_users() == {}
