"""Tests for dashboard authentication credential loading."""

from atlas.core.config import get_settings
from atlas.dashboard.auth import get_users


def _reset_cached_state() -> None:
    """Reset cached config/secrets state for deterministic tests."""
    get_settings.cache_clear()

    # Reset secrets manager singleton cache used by get_secret().
    import atlas.core.secrets as secrets_module

    secrets_module._manager = None


def test_get_users_uses_dev_default_credentials(monkeypatch) -> None:
    """Development environment should keep local fallback credentials."""
    monkeypatch.setenv("ATLAS_ENV", "development")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    _reset_cached_state()

    users = get_users()

    assert set(users.keys()) == {"admin", "analyst"}
    assert users["admin"] == users["analyst"]
    assert len(users["admin"]) == 64  # SHA-256 hex digest


def test_get_users_fails_closed_in_production_when_missing(monkeypatch) -> None:
    """Production must not fall back to hardcoded credentials."""
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    _reset_cached_state()

    users = get_users()

    assert users == {}


def test_get_users_accepts_explicit_env_credentials_in_production(monkeypatch) -> None:
    """Production should authenticate only when explicit credentials are configured."""
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv(
        "ATLAS_DASHBOARD_USERS",
        '{"ops":"2bb80d537b1da3e38bd30361aa855686bde0baef6fdb6f8f7f3f6f5f5f5f5f5f"}',
    )
    _reset_cached_state()

    users = get_users()

    assert users == {
        "ops": "2bb80d537b1da3e38bd30361aa855686bde0baef6fdb6f8f7f3f6f5f5f5f5f5f5f"
    }
