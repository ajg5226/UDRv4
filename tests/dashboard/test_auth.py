import json

from atlas.core.config import reload_settings
from atlas.dashboard.auth import get_users, hash_password, verify_password


def _reset_env(monkeypatch) -> None:
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.delenv("ATLAS_ENV", raising=False)
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)
    reload_settings()


def test_get_users_fails_closed_in_production_without_credentials(monkeypatch) -> None:
    _reset_env(monkeypatch)
    monkeypatch.setenv("ATLAS_ENV", "production")
    reload_settings()

    assert get_users() == {}


def test_get_users_uses_defaults_in_development(monkeypatch) -> None:
    _reset_env(monkeypatch)
    monkeypatch.setenv("ATLAS_ENV", "development")
    reload_settings()

    users = get_users()

    assert "admin" in users
    assert "analyst" in users
    assert verify_password("admin", "atlas123")


def test_verify_password_uses_env_credentials_in_production(monkeypatch) -> None:
    _reset_env(monkeypatch)
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv(
        "ATLAS_DASHBOARD_USERS",
        json.dumps({"alice": hash_password("S3curePassword!")}),
    )
    reload_settings()

    assert verify_password("alice", "S3curePassword!")
    assert not verify_password("alice", "wrong-password")
