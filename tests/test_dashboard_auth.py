import hashlib
from types import SimpleNamespace

import pytest

from atlas.dashboard import auth


def _settings(environment: str) -> SimpleNamespace:
    return SimpleNamespace(
        environment=environment,
        dashboard=SimpleNamespace(
            auth=SimpleNamespace(users_secret="atlas-dashboard-users"),
        ),
    )


def test_get_users_uses_env_var_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr(auth, "get_secret", lambda _name: None)
    monkeypatch.setenv(
        "ATLAS_DASHBOARD_USERS",
        '{"alice":"abc123","bob":"def456"}',
    )

    users = auth.get_users()

    assert users == {"alice": "abc123", "bob": "def456"}


def test_get_users_fails_closed_in_production_without_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr(auth, "get_secret", lambda _name: None)
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)

    users = auth.get_users()

    assert users == {}


def test_get_users_allows_dev_defaults_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("development"))
    monkeypatch.setattr(auth, "get_secret", lambda _name: None)
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)

    users = auth.get_users()

    expected_hash = hashlib.sha256("atlas123".encode()).hexdigest()
    assert users["admin"] == expected_hash
    assert users["analyst"] == expected_hash


def test_verify_password_rejects_in_production_without_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr(auth, "get_secret", lambda _name: None)
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)

    assert auth.verify_password("admin", "atlas123") is False
