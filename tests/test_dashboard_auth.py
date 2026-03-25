import hashlib

from atlas.core.config import reload_settings
from atlas.dashboard.auth import get_users, verify_password


def test_get_users_returns_default_in_development(monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "development")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    reload_settings()

    users = get_users()

    expected_hash = hashlib.sha256("atlas123".encode()).hexdigest()
    assert users == {"admin": expected_hash, "analyst": expected_hash}


def test_get_users_fails_closed_in_production_without_users(monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    reload_settings()

    users = get_users()

    assert users == {}
    assert verify_password("admin", "atlas123") is False


def test_get_users_fails_closed_in_production_with_invalid_json(monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "{invalid-json")
    reload_settings()

    users = get_users()

    assert users == {}


def test_get_users_uses_configured_hashes(monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    password_hash = hashlib.sha256("secret-pass".encode()).hexdigest()
    monkeypatch.setenv(
        "ATLAS_DASHBOARD_USERS",
        f'{{"alice":"{password_hash}"}}',
    )
    reload_settings()

    users = get_users()

    assert users == {"alice": password_hash}
    assert verify_password("alice", "secret-pass") is True
    assert verify_password("alice", "wrong-pass") is False
