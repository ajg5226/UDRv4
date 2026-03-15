"""Unit tests for dashboard authentication behavior."""

import json
from types import SimpleNamespace

from atlas.dashboard import auth


def _settings(environment: str) -> SimpleNamespace:
    """Build a minimal settings object needed by auth.get_users."""
    return SimpleNamespace(
        environment=environment,
        dashboard=SimpleNamespace(
            auth=SimpleNamespace(users_secret="atlas-dashboard-users"),
        ),
    )


def test_get_users_uses_explicit_env_json(monkeypatch) -> None:
    users = {"alice": auth.hash_password("pw1"), "bob": auth.hash_password("pw2")}
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", json.dumps(users))
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))

    loaded = auth.get_users()

    assert loaded == users


def test_get_users_fails_closed_in_production_without_config(monkeypatch) -> None:
    import atlas.core.secrets as secrets

    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr(secrets, "get_secret", lambda _name: None)

    loaded = auth.get_users()

    assert loaded == {}


def test_get_users_in_production_can_load_secret(monkeypatch) -> None:
    import atlas.core.secrets as secrets

    secret_users = {"prod_admin": auth.hash_password("strong-password")}
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr(secrets, "get_secret", lambda _name: json.dumps(secret_users))

    loaded = auth.get_users()

    assert loaded == secret_users


def test_get_users_returns_dev_defaults_in_development(monkeypatch) -> None:
    import atlas.core.secrets as secrets

    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("development"))
    monkeypatch.setattr(secrets, "get_secret", lambda _name: None)

    loaded = auth.get_users()

    assert set(loaded.keys()) == {"admin", "analyst"}
    assert auth.verify_password("admin", "atlas123")
    assert auth.verify_password("analyst", "atlas123")


def test_invalid_env_json_does_not_enable_defaults_in_production(monkeypatch) -> None:
    import atlas.core.secrets as secrets

    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "{not-json")
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr(secrets, "get_secret", lambda _name: None)

    loaded = auth.get_users()

    assert loaded == {}
