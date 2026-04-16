"""Security-focused tests for dashboard authentication defaults."""

import types

from atlas.dashboard import auth


def _settings(environment: str) -> types.SimpleNamespace:
    """Build a minimal settings object for auth tests."""
    return types.SimpleNamespace(
        environment=environment,
        dashboard=types.SimpleNamespace(
            auth=types.SimpleNamespace(users_secret="atlas-dashboard-users")
        ),
    )


def test_get_users_uses_environment_variable(monkeypatch):
    """Explicit env credentials should override all fallbacks."""
    custom_hash = auth.hash_password("supersecret")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", '{"svc":"%s"}' % custom_hash)
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))

    users = auth.get_users()

    assert users == {"svc": custom_hash}


def test_get_users_falls_back_to_dev_defaults(monkeypatch):
    """Development mode keeps local defaults for quickstart usability."""
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("development"))

    users = auth.get_users()

    assert set(users.keys()) == {"admin", "analyst"}
    assert auth.verify_password("admin", "atlas123")


def test_get_users_fails_closed_in_production_without_config(monkeypatch):
    """Production mode must not expose built-in credentials."""
    from atlas.core import secrets

    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr(secrets, "get_secret", lambda _name: None)

    users = auth.get_users()

    assert users == {}
    assert not auth.verify_password("admin", "atlas123")


def test_get_users_loads_key_vault_secret_in_production(monkeypatch):
    """Configured secrets should provide valid production users."""
    from atlas.core import secrets

    svc_hash = auth.hash_password("production-password")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr(secrets, "get_secret", lambda _name: '{"svc":"%s"}' % svc_hash)

    users = auth.get_users()

    assert users == {"svc": svc_hash}
    assert auth.verify_password("svc", "production-password")
