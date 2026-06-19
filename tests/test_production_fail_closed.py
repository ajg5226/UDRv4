"""Regression tests for production fail-closed safety checks."""

import hashlib
import json

import pytest

from atlas.core import config as config_module
from atlas.core import secrets as secrets_module
from atlas.core.exceptions import ConfigurationError
from atlas.dashboard import auth
from atlas.storage.database import Database, reset_database


def _reset_cached_state() -> None:
    config_module.get_settings.cache_clear()
    secrets_module._manager = None
    reset_database()


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch):
    for env_var in [
        "ATLAS_ENV",
        "ATLAS_DASHBOARD_USERS",
        "ATLAS_DB_CONNECTION",
        "ATLAS_KEYVAULT_URL",
    ]:
        monkeypatch.delenv(env_var, raising=False)
    _reset_cached_state()
    yield
    _reset_cached_state()


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def test_dashboard_users_fail_closed_without_production_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    _reset_cached_state()

    with pytest.raises(ConfigurationError, match="Dashboard users must be configured"):
        auth.get_users()


def test_dashboard_users_do_not_fall_back_on_invalid_production_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "not-json")
    _reset_cached_state()

    with pytest.raises(ConfigurationError, match="not valid JSON"):
        auth.get_users()


def test_dashboard_users_accept_valid_production_environment_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv(
        "ATLAS_DASHBOARD_USERS",
        json.dumps({"admin": _hash_password("correct horse battery staple")}),
    )
    _reset_cached_state()

    assert auth.verify_password("admin", "correct horse battery staple") is True
    assert auth.verify_password("admin", "atlas123") is False


def test_dashboard_users_accept_valid_production_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setattr(
        auth,
        "get_secret",
        lambda name: json.dumps({"analyst": _hash_password("from-key-vault")}),
    )
    _reset_cached_state()

    assert auth.verify_password("analyst", "from-key-vault") is True
    assert auth.verify_password("analyst", "atlas123") is False


def test_development_dashboard_defaults_remain_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "development")
    _reset_cached_state()

    assert auth.verify_password("admin", "atlas123") is True


def test_database_connection_fails_closed_without_production_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    _reset_cached_state()

    with pytest.raises(ConfigurationError, match="Database connection string must be configured"):
        Database()


def test_database_uses_local_sqlite_only_in_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "development")
    _reset_cached_state()

    assert Database()._connection_string == "sqlite:///atlas_dev.db"


def test_database_accepts_explicit_production_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DB_CONNECTION", "sqlite:///explicit-prod-test.db")
    _reset_cached_state()

    assert Database()._connection_string == "sqlite:///explicit-prod-test.db"
