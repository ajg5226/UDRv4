import json

import pytest

import atlas.core.secrets as secrets_module
from atlas.core.config import get_settings
from atlas.core.exceptions import ConfigurationError
from atlas.dashboard.auth import get_users, hash_password, verify_password


def reset_auth_config(monkeypatch: pytest.MonkeyPatch, environment: str) -> None:
    monkeypatch.setenv("ATLAS_ENV", environment)
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)
    monkeypatch.setattr(secrets_module, "_manager", None)
    get_settings.cache_clear()


def test_development_uses_default_dashboard_users(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_auth_config(monkeypatch, "development")

    users = get_users()

    assert users == {
        "admin": hash_password("atlas123"),
        "analyst": hash_password("atlas123"),
    }
    assert verify_password("admin", "atlas123")


def test_production_without_dashboard_users_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_auth_config(monkeypatch, "production")

    with pytest.raises(ConfigurationError, match="Dashboard users are not configured"):
        get_users()

    with pytest.raises(ConfigurationError, match="Dashboard users are not configured"):
        verify_password("admin", "atlas123")


def test_production_uses_configured_dashboard_users(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_auth_config(monkeypatch, "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", json.dumps({"admin": hash_password("stronger")}))

    assert get_users() == {"admin": hash_password("stronger")}
    assert verify_password("admin", "stronger")
    assert not verify_password("admin", "atlas123")


def test_production_rejects_malformed_dashboard_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_auth_config(monkeypatch, "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "not-json")

    with pytest.raises(ConfigurationError, match="Invalid dashboard users configuration"):
        get_users()
