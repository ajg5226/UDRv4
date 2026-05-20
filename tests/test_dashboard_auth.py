import json

import pytest

from atlas.core.config import get_settings
from atlas.dashboard import auth


@pytest.fixture(autouse=True)
def clear_auth_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_production_auth_fails_closed_without_configured_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setattr(auth, "get_secret", lambda name: None)

    with pytest.raises(
        auth.DashboardAuthConfigurationError,
        match="Dashboard users must be configured",
    ):
        auth.get_users()


def test_production_auth_loads_users_from_configured_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    password_hash = auth.hash_password("correct horse battery staple")
    secret_names: list[str] = []

    def get_configured_secret(name: str) -> str:
        secret_names.append(name)
        return json.dumps({"admin": password_hash})

    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setattr(auth, "get_secret", get_configured_secret)

    assert auth.get_users() == {"admin": password_hash}
    assert auth.verify_password("admin", "correct horse battery staple")
    assert secret_names == ["atlas-dashboard-users", "atlas-dashboard-users"]


def test_invalid_dashboard_users_json_is_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "not-json")

    with pytest.raises(
        auth.DashboardAuthConfigurationError,
        match="Invalid dashboard users JSON",
    ):
        auth.get_users()


def test_development_auth_uses_local_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "development")
    monkeypatch.setattr(auth, "get_secret", lambda name: None)

    assert auth.verify_password("admin", "atlas123")
