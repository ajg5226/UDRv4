"""Tests for dashboard authentication credential loading behavior."""

from types import SimpleNamespace

from atlas.dashboard import auth


def _make_settings(environment: str, users_secret: str = "atlas-dashboard-users"):
    return SimpleNamespace(
        environment=environment,
        dashboard=SimpleNamespace(
            auth=SimpleNamespace(
                users_secret=users_secret,
            )
        ),
    )


def test_get_users_production_fails_closed_without_config(monkeypatch):
    """Production must not fall back to default credentials."""
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: _make_settings("production"))
    monkeypatch.setattr("atlas.core.secrets.get_secret", lambda *_args, **_kwargs: None)

    users = auth.get_users()

    assert users == {}
    assert auth.verify_password("admin", "atlas123") is False


def test_get_users_production_fails_closed_on_malformed_env_users(monkeypatch):
    """Malformed production credentials config should reject all logins."""
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "{not-json")
    monkeypatch.setattr(auth, "get_settings", lambda: _make_settings("production"))
    monkeypatch.setattr("atlas.core.secrets.get_secret", lambda *_args, **_kwargs: None)

    users = auth.get_users()

    assert users == {}
    assert auth.verify_password("admin", "atlas123") is False


def test_get_users_production_accepts_valid_secret_payload(monkeypatch):
    """Production should authenticate with configured secret payload."""
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: _make_settings("production"))
    hashed = auth.hash_password("strong-password")
    monkeypatch.setattr(
        "atlas.core.secrets.get_secret",
        lambda *_args, **_kwargs: f'{{"ops":"{hashed}"}}',
    )

    users = auth.get_users()

    assert users == {"ops": hashed}
    assert auth.verify_password("ops", "strong-password") is True


def test_get_users_development_keeps_default_fallback(monkeypatch):
    """Development retains default credentials for local setup."""
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: _make_settings("development"))
    monkeypatch.setattr("atlas.core.secrets.get_secret", lambda *_args, **_kwargs: None)

    users = auth.get_users()

    assert "admin" in users
    assert auth.verify_password("admin", "atlas123") is True
