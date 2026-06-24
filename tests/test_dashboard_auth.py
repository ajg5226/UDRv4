import json

import pytest

from atlas.core.config import get_settings
from atlas.dashboard.auth import (
    get_users,
    hash_password,
    using_development_default_users,
    verify_password,
)


@pytest.fixture(autouse=True)
def reset_auth_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_development_defaults_are_available_without_configured_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "development")
    get_settings.cache_clear()

    assert verify_password("admin", "atlas123")
    assert using_development_default_users()


def test_production_without_configured_users_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    get_settings.cache_clear()

    assert get_users() == {}
    assert not verify_password("admin", "atlas123")
    assert not using_development_default_users()


def test_malformed_configured_users_fail_closed_even_in_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "development")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "{not valid json")
    get_settings.cache_clear()

    assert get_users() == {}
    assert not verify_password("admin", "atlas123")
    assert not using_development_default_users()


def test_configured_users_replace_development_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv(
        "ATLAS_DASHBOARD_USERS",
        json.dumps({"alice": hash_password("correct horse battery staple")}),
    )
    get_settings.cache_clear()

    assert verify_password("alice", "correct horse battery staple")
    assert not verify_password("admin", "atlas123")
    assert not using_development_default_users()
