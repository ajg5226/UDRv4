import hashlib
import json
import sys
import types
from types import SimpleNamespace

sys.modules.setdefault("streamlit", types.SimpleNamespace(session_state={}))

from atlas.dashboard import auth


def _settings(environment: str) -> SimpleNamespace:
    return SimpleNamespace(
        environment=environment,
        dashboard=SimpleNamespace(
            auth=SimpleNamespace(users_secret="atlas-dashboard-users"),
        ),
    )


def test_get_users_fails_closed_in_production_without_credentials(monkeypatch) -> None:
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr("atlas.core.secrets.get_secret", lambda _: None)

    assert auth.get_users() == {}


def test_get_users_uses_dev_defaults(monkeypatch) -> None:
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("development"))
    monkeypatch.setattr("atlas.core.secrets.get_secret", lambda _: None)

    users = auth.get_users()
    assert set(users) == {"admin", "analyst"}
    assert auth.verify_password("admin", "atlas123")


def test_verify_password_accepts_secret_backed_users_in_production(monkeypatch) -> None:
    password_hash = hashlib.sha256("s3cr3t".encode()).hexdigest()
    users_payload = json.dumps({"ops-admin": password_hash})

    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr("atlas.core.secrets.get_secret", lambda _: users_payload)

    assert auth.verify_password("ops-admin", "s3cr3t")
    assert not auth.verify_password("ops-admin", "wrong-password")
