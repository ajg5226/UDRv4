from types import SimpleNamespace

import pytest

from atlas.dashboard import auth
from atlas.dashboard.auth import DashboardAuthConfigurationError


def _settings(environment: str = "production") -> SimpleNamespace:
    return SimpleNamespace(
        environment=environment,
        dashboard=SimpleNamespace(
            auth=SimpleNamespace(users_secret="atlas-dashboard-users")
        ),
    )


def test_production_auth_requires_configured_users(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr(auth, "get_secret", lambda name: None)

    with pytest.raises(DashboardAuthConfigurationError):
        auth.get_users()


def test_production_auth_rejects_malformed_users(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr(auth, "get_secret", lambda name: "not-json")

    with pytest.raises(DashboardAuthConfigurationError):
        auth.get_users()


def test_production_auth_loads_configured_secret_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    password_hash = auth.hash_password("correct-horse-battery-staple")
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr(
        auth,
        "get_secret",
        lambda name: f'{{"admin":"{password_hash}"}}',
    )

    assert auth.verify_password("admin", "correct-horse-battery-staple") is True
    assert auth.verify_password("admin", "atlas123") is False


def test_development_auth_can_use_default_users(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("development"))
    monkeypatch.setattr(auth, "get_secret", lambda name: None)

    assert auth.verify_password("admin", "atlas123") is True
