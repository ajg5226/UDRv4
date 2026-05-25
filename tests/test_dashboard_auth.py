import hashlib
import json

import pytest

from atlas.core.config import get_settings
from atlas.core.exceptions import ConfigurationError


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_dashboard_users_fail_closed_in_production(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)

    from atlas.dashboard.auth import get_users

    with pytest.raises(ConfigurationError):
        get_users()


def test_dashboard_users_load_from_configured_secret(monkeypatch):
    password_hash = hashlib.sha256(b"safe-password").hexdigest()
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", json.dumps({"admin": password_hash}))
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)

    from atlas.dashboard.auth import get_users, verify_password

    assert get_users() == {"admin": password_hash}
    assert verify_password("admin", "safe-password") is True


def test_invalid_dashboard_users_fail_closed_in_production(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "not-json")
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)

    from atlas.dashboard.auth import get_users

    with pytest.raises(ConfigurationError):
        get_users()


def test_development_dashboard_defaults_remain_available(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "development")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)

    from atlas.dashboard.auth import get_users, verify_password

    assert set(get_users()) == {"admin", "analyst"}
    assert verify_password("admin", "atlas123") is True
