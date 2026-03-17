"""Tests for dashboard authentication credential loading."""

import hashlib
import json

import pytest

from atlas.core.config import reload_settings
from atlas.dashboard import auth


@pytest.fixture(autouse=True)
def reset_auth_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure each test controls auth-related environment variables."""
    monkeypatch.delenv("ATLAS_ENV", raising=False)
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    reload_settings()
    yield
    monkeypatch.delenv("ATLAS_ENV", raising=False)
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    reload_settings()


def test_get_users_uses_dev_defaults_in_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "development")
    reload_settings()

    users = auth.get_users()

    expected_hash = hashlib.sha256("atlas123".encode()).hexdigest()
    assert users == {"admin": expected_hash, "analyst": expected_hash}


def test_get_users_fails_closed_in_production_when_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    reload_settings()

    assert auth.get_users() == {}


def test_get_users_fails_closed_in_production_for_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "{not-valid-json")
    reload_settings()

    assert auth.get_users() == {}


def test_verify_password_uses_configured_credentials_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv(
        "ATLAS_DASHBOARD_USERS",
        json.dumps({"ops": hashlib.sha256("strong-pass".encode()).hexdigest()}),
    )
    reload_settings()

    assert auth.verify_password("ops", "strong-pass") is True
    assert auth.verify_password("ops", "wrong-pass") is False
