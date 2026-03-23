import hashlib
from types import SimpleNamespace

import pytest

from atlas.core.exceptions import AuthenticationError
from atlas.dashboard import auth


def _settings(environment: str) -> SimpleNamespace:
    return SimpleNamespace(
        environment=environment,
        dashboard=SimpleNamespace(
            auth=SimpleNamespace(users_secret="atlas-dashboard-users"),
        ),
    )


def test_get_users_loads_from_configured_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr(auth, "get_secret", lambda name: '{"alice":"abc123"}')

    users = auth.get_users()

    assert users == {"alice": "abc123"}


def test_get_users_raises_on_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "{not-json")
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("development"))

    with pytest.raises(AuthenticationError):
        auth.get_users()


def test_get_users_requires_explicit_credentials_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr(auth, "get_secret", lambda name: None)

    with pytest.raises(AuthenticationError):
        auth.get_users()


def test_get_users_falls_back_to_defaults_in_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("development"))
    monkeypatch.setattr(auth, "get_secret", lambda name: None)

    users = auth.get_users()
    expected_hash = hashlib.sha256("atlas123".encode()).hexdigest()

    assert users == {"admin": expected_hash, "analyst": expected_hash}
