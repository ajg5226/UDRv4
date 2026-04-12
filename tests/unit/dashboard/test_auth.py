import hashlib
import json

import pytest

import atlas.dashboard.auth as auth
from atlas.core.config import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_development_uses_default_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "development")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)

    users = auth.get_users()

    assert "admin" in users
    assert auth.verify_password("admin", "atlas123")


def test_production_fails_closed_without_configured_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr("atlas.core.secrets.get_secret", lambda name, default=None: None)

    users = auth.get_users()

    assert users == {}
    assert not auth.verify_password("admin", "atlas123")


def test_production_uses_secret_backed_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)

    password_hash = hashlib.sha256("super-secret".encode()).hexdigest()
    users_json = json.dumps({"secure-user": password_hash})
    monkeypatch.setattr("atlas.core.secrets.get_secret", lambda name, default=None: users_json)

    users = auth.get_users()

    assert users == {"secure-user": password_hash}
    assert auth.verify_password("secure-user", "super-secret")
