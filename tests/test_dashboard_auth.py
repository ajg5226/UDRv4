import pytest

from atlas.core.config import get_settings
from atlas.core.exceptions import ConfigurationError
from atlas.dashboard import auth


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_development_uses_default_dashboard_users(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "development")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_secret", lambda name: None)

    users = auth.get_users()

    assert users == {
        "admin": auth.hash_password("atlas123"),
        "analyst": auth.hash_password("atlas123"),
    }


def test_production_requires_configured_dashboard_users(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_secret", lambda name: None)

    with pytest.raises(ConfigurationError, match="Dashboard users are not configured"):
        auth.get_users()


def test_production_loads_dashboard_users_from_key_vault_secret(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(
        auth,
        "get_secret",
        lambda name: '{"operator":"%s"}' % auth.hash_password("safe-password"),
    )

    assert auth.get_users() == {"operator": auth.hash_password("safe-password")}


def test_malformed_dashboard_users_do_not_fall_back_to_defaults(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "{not-valid-json")

    with pytest.raises(ConfigurationError, match="Invalid dashboard users JSON"):
        auth.get_users()
