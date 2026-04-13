import json
from types import SimpleNamespace

from atlas.dashboard import auth


def _settings(environment: str) -> SimpleNamespace:
    return SimpleNamespace(
        environment=environment,
        dashboard=SimpleNamespace(
            auth=SimpleNamespace(users_secret="atlas-dashboard-users")
        ),
    )


def test_get_users_defaults_in_development(monkeypatch) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("development"))
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)

    users = auth.get_users()

    assert set(users.keys()) == {"admin", "analyst"}
    assert auth.verify_password("admin", "atlas123")


def test_get_users_fails_closed_in_production_without_credentials(monkeypatch) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)

    assert auth.get_users() == {}
    assert not auth.verify_password("admin", "atlas123")


def test_get_users_fails_closed_in_production_with_invalid_json(monkeypatch) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "{not-json")

    assert auth.get_users() == {}


def test_get_users_honors_production_credentials(monkeypatch) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    users = {"ops": auth.hash_password("safe-password")}
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", json.dumps(users))

    assert auth.verify_password("ops", "safe-password")
