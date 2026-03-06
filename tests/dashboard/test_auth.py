"""Tests for dashboard authentication behavior."""

from types import SimpleNamespace

from atlas.dashboard import auth


def _set_environment(monkeypatch, environment: str) -> None:
    """Override settings environment for auth tests."""
    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(environment=environment))


def test_development_uses_default_credentials(monkeypatch) -> None:
    """Development mode should allow built-in local credentials."""
    _set_environment(monkeypatch, "development")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)

    assert auth.verify_password("admin", "atlas123")
    assert auth.verify_password("analyst", "atlas123")


def test_production_without_credentials_fails_closed(monkeypatch) -> None:
    """Production mode must not fall back to known default credentials."""
    _set_environment(monkeypatch, "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)

    assert auth.get_users() == {}
    assert not auth.verify_password("admin", "atlas123")


def test_production_with_invalid_credentials_json_fails_closed(monkeypatch) -> None:
    """Malformed credential configuration should not allow login."""
    _set_environment(monkeypatch, "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "{not-valid-json}")

    assert auth.get_users() == {}
    assert not auth.verify_password("admin", "atlas123")


def test_production_with_valid_credentials_works(monkeypatch) -> None:
    """Configured production credentials should authenticate correctly."""
    _set_environment(monkeypatch, "production")
    password_hash = auth.hash_password("strong-password")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", f'{{"ops":"{password_hash}"}}')

    assert auth.verify_password("ops", "strong-password")
    assert not auth.verify_password("ops", "wrong-password")
