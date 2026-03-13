import hashlib
import json

import pytest

from atlas.core.config import get_settings
from atlas.dashboard.auth import get_users, verify_password


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_production_without_users_rejects_default_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr("atlas.core.secrets.get_secret", lambda *args, **kwargs: None)

    users = get_users()

    assert users == {}
    assert verify_password("admin", "atlas123") is False


def test_production_with_invalid_json_rejects_login(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "{not-valid-json")

    users = get_users()

    assert users == {}
    assert verify_password("admin", "atlas123") is False


def test_development_allows_default_users(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "development")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr("atlas.core.secrets.get_secret", lambda *args, **kwargs: None)

    users = get_users()

    assert "admin" in users
    assert verify_password("admin", "atlas123") is True


def test_production_accepts_configured_user_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv(
        "ATLAS_DASHBOARD_USERS",
        json.dumps({"alice": hashlib.sha256("s3cret".encode()).hexdigest()}),
    )

    users = get_users()

    assert users["alice"]
    assert verify_password("alice", "s3cret") is True
