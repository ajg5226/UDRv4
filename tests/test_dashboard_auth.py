import json
import sys
import types
from types import SimpleNamespace

sys.modules.setdefault("streamlit", SimpleNamespace(session_state={}))
fake_config = types.ModuleType("atlas.core.config")
fake_secrets = types.ModuleType("atlas.core.secrets")
fake_config.get_settings = lambda: SimpleNamespace(
    environment="development",
    dashboard=SimpleNamespace(auth=SimpleNamespace(users_secret="atlas-dashboard-users")),
)
fake_secrets.get_secret = lambda _: None
sys.modules.setdefault("atlas.core.config", fake_config)
sys.modules.setdefault("atlas.core.secrets", fake_secrets)

from atlas.dashboard import auth


def _settings(environment: str) -> SimpleNamespace:
    return SimpleNamespace(
        environment=environment,
        dashboard=SimpleNamespace(
            auth=SimpleNamespace(users_secret="atlas-dashboard-users"),
        ),
    )


def test_get_users_defaults_only_in_development(monkeypatch) -> None:
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("development"))
    monkeypatch.setattr(auth, "get_secret", lambda _: None)

    users = auth.get_users()

    assert sorted(users.keys()) == ["admin", "analyst"]
    assert auth.verify_password("admin", "atlas123")


def test_get_users_fails_closed_in_production_without_credentials(monkeypatch) -> None:
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr(auth, "get_secret", lambda _: None)

    assert auth.get_users() == {}
    assert not auth.verify_password("admin", "atlas123")


def test_get_users_loads_secret_payload_in_production(monkeypatch) -> None:
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))

    password_hash = auth.hash_password("strong-password")
    secret_payload = json.dumps({"ops-admin": password_hash})
    monkeypatch.setattr(auth, "get_secret", lambda _: secret_payload)

    users = auth.get_users()

    assert users == {"ops-admin": password_hash}
    assert auth.verify_password("ops-admin", "strong-password")
