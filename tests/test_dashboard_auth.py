import json

import pytest

from atlas.core.config import get_settings
from atlas.dashboard import auth


@pytest.fixture(autouse=True)
def clear_settings_cache(monkeypatch: pytest.MonkeyPatch):
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

    with pytest.raises(RuntimeError, match="Dashboard users must be configured"):
        auth.get_users()


def test_production_auth_loads_users_from_configured_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    password_hash = auth.hash_password("correct horse battery staple")
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setattr(auth, "get_secret", lambda name: json.dumps({"admin": password_hash}))

    assert auth.get_users() == {"admin": password_hash}


def test_invalid_dashboard_users_json_is_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "not-json")

    with pytest.raises(ValueError, match="Invalid dashboard users JSON"):
        auth.get_users()
