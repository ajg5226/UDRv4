"""Authentication safety tests for dashboard login."""

from atlas.core.config import get_settings
from atlas.dashboard import auth


def _reset_settings_cache() -> None:
    get_settings.cache_clear()


def test_development_uses_default_credentials(monkeypatch) -> None:
    """Development mode should keep explicit fallback credentials."""
    monkeypatch.setenv("ATLAS_ENV", "development")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_secret", lambda _name: None)
    _reset_settings_cache()

    users = auth.get_users()
    assert "admin" in users
    assert auth.verify_password("admin", "atlas123")


def test_production_without_credentials_fails_closed(monkeypatch) -> None:
    """Production mode must not permit hardcoded fallback credentials."""
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_secret", lambda _name: None)
    _reset_settings_cache()

    users = auth.get_users()
    assert users == {}
    assert not auth.verify_password("admin", "atlas123")


def test_production_uses_configured_secret_users(monkeypatch) -> None:
    """Production mode should authenticate using configured secret users."""
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(
        auth,
        "get_secret",
        lambda _name: '{"ops":"' + auth.hash_password("s3cure") + '"}',
    )
    _reset_settings_cache()

    users = auth.get_users()
    assert "ops" in users
    assert auth.verify_password("ops", "s3cure")
