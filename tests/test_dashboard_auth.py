"""Regression tests for dashboard authentication hardening."""

from types import SimpleNamespace

from atlas.dashboard import auth


def _settings(environment: str) -> SimpleNamespace:
    """Build a minimal settings object used by dashboard auth."""
    return SimpleNamespace(
        environment=environment,
        dashboard=SimpleNamespace(
            auth=SimpleNamespace(users_secret="atlas-dashboard-users"),
        ),
    )


def test_get_users_prefers_environment_json(monkeypatch) -> None:
    """Explicit env credentials should be loaded as-is."""
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr(auth, "get_secret", lambda _name: None)
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", '{"alice":"abc123"}')

    assert auth.get_users() == {"alice": "abc123"}


def test_get_users_uses_secret_when_env_missing(monkeypatch) -> None:
    """Configured secret users should be accepted when env var is absent."""
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr(
        auth,
        "get_secret",
        lambda _name: '{"service-admin":"deadbeef"}',
    )
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)

    assert auth.get_users() == {"service-admin": "deadbeef"}


def test_production_fails_closed_without_credentials(monkeypatch) -> None:
    """Production must not fall back to hardcoded default users."""
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr(auth, "get_secret", lambda _name: None)
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)

    assert auth.get_users() == {}
    assert auth.verify_password("admin", "atlas123") is False


def test_development_keeps_default_credentials(monkeypatch) -> None:
    """Development keeps convenience defaults for local onboarding."""
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("development"))
    monkeypatch.setattr(auth, "get_secret", lambda _name: None)
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)

    assert auth.verify_password("admin", "atlas123") is True
    assert auth.verify_password("analyst", "atlas123") is True
