"""Regression tests for dashboard authentication credential loading."""

from types import SimpleNamespace

from atlas.dashboard import auth


def _settings(environment: str = "development", users_secret: str = "atlas-dashboard-users"):
    return SimpleNamespace(
        environment=environment,
        dashboard=SimpleNamespace(
            auth=SimpleNamespace(users_secret=users_secret),
        ),
    )


def test_get_users_production_fails_closed_without_credentials(monkeypatch):
    """Production should not fall back to default development credentials."""
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: _settings(environment="production"))
    monkeypatch.setattr(auth, "get_secret", lambda _: None)

    users = auth.get_users()

    assert users == {}
    assert auth.verify_password("admin", "atlas123") is False


def test_get_users_development_uses_default_credentials(monkeypatch):
    """Development keeps convenient defaults when explicit credentials are absent."""
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: _settings(environment="development"))
    monkeypatch.setattr(auth, "get_secret", lambda _: None)

    users = auth.get_users()

    assert "admin" in users
    assert auth.verify_password("admin", "atlas123") is True


def test_get_users_production_accepts_secret_when_env_invalid(monkeypatch):
    """Invalid env JSON should fall back to valid secret credentials."""
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "{invalid_json")
    monkeypatch.setattr(auth, "get_settings", lambda: _settings(environment="production"))
    monkeypatch.setattr(
        auth,
        "get_secret",
        lambda _: '{"admin":"240be518fabd2724ddb6f04eeb4f2f17bfdb76d9d9fcca832ebf89d1ed2022ef"}',
    )

    users = auth.get_users()

    assert users == {
        "admin": "240be518fabd2724ddb6f04eeb4f2f17bfdb76d9d9fcca832ebf89d1ed2022ef"
    }
    assert auth.verify_password("admin", "atlas123") is True
