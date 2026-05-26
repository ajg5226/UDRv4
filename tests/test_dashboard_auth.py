import json

import pytest

from atlas.core.config import get_settings
from atlas.core.exceptions import ConfigurationError
from atlas.dashboard import auth


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_production_requires_configured_dashboard_users(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_secret", lambda name: None)

    with pytest.raises(ConfigurationError):
        auth.get_users()


def test_production_rejects_malformed_dashboard_users(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "{bad json")
    monkeypatch.setattr(auth, "get_secret", lambda name: None)

    with pytest.raises(ConfigurationError):
        auth.get_users()


def test_production_loads_dashboard_users_from_secret(monkeypatch):
    password_hash = auth.hash_password("s3cret")

    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_secret", lambda name: json.dumps({"ops": password_hash}))

    assert auth.verify_password("ops", "s3cret") is True
    assert auth.verify_password("admin", "atlas123") is False


def test_development_defaults_remain_available(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "development")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_secret", lambda name: None)

    assert auth.verify_password("admin", "atlas123") is True
