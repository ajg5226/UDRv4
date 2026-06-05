import json

import pytest

from atlas.core.config import get_settings
from atlas.dashboard import auth


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch):
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.delenv("ATLAS_ENV", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_development_uses_default_credentials(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "development")
    monkeypatch.setattr("atlas.core.secrets.get_secret", lambda name: None)
    get_settings.cache_clear()

    assert auth.verify_password("admin", "atlas123") is True
    assert auth.verify_password("admin", "wrong") is False


def test_production_without_configured_users_fails_closed(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setattr("atlas.core.secrets.get_secret", lambda name: None)
    get_settings.cache_clear()

    with pytest.raises(auth.AuthConfigurationError, match="Dashboard users are not configured"):
        auth.get_users()

    with pytest.raises(auth.AuthConfigurationError):
        auth.verify_password("admin", "atlas123")


def test_production_loads_users_from_configured_secret(monkeypatch):
    password_hash = auth.hash_password("correct horse battery staple")
    secret_value = json.dumps({"portfolio-admin": password_hash})

    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setattr("atlas.core.secrets.get_secret", lambda name: secret_value)
    get_settings.cache_clear()

    assert auth.verify_password("portfolio-admin", "correct horse battery staple") is True
    assert auth.verify_password("admin", "atlas123") is False


def test_environment_users_override_secret(monkeypatch):
    env_password_hash = auth.hash_password("from-env")
    secret_password_hash = auth.hash_password("from-secret")

    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", json.dumps({"env-user": env_password_hash}))
    monkeypatch.setattr(
        "atlas.core.secrets.get_secret",
        lambda name: json.dumps({"secret-user": secret_password_hash}),
    )
    get_settings.cache_clear()

    assert auth.verify_password("env-user", "from-env") is True
    assert auth.verify_password("secret-user", "from-secret") is False
