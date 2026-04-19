import hashlib
import json

from atlas.dashboard import auth


class _Settings:
    def __init__(self, environment: str) -> None:
        self.environment = environment


def _set_environment(monkeypatch, environment: str) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: _Settings(environment))


def test_get_users_allows_defaults_in_development(monkeypatch) -> None:
    _set_environment(monkeypatch, "development")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)

    users = auth.get_users()

    expected_hash = hashlib.sha256("atlas123".encode()).hexdigest()
    assert users["admin"] == expected_hash
    assert users["analyst"] == expected_hash


def test_get_users_fails_closed_in_production_without_credentials(monkeypatch) -> None:
    _set_environment(monkeypatch, "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)

    users = auth.get_users()

    assert users == {}


def test_get_users_fails_closed_in_production_on_malformed_credentials(monkeypatch) -> None:
    _set_environment(monkeypatch, "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "{not-valid-json")

    users = auth.get_users()

    assert users == {}


def test_get_users_uses_configured_credentials_in_production(monkeypatch) -> None:
    _set_environment(monkeypatch, "production")
    password_hash = hashlib.sha256("safe-password".encode()).hexdigest()
    monkeypatch.setenv(
        "ATLAS_DASHBOARD_USERS",
        json.dumps({"prod-user": password_hash}),
    )

    users = auth.get_users()

    assert users == {"prod-user": password_hash}


def test_verify_password_rejects_default_credentials_in_production(monkeypatch) -> None:
    _set_environment(monkeypatch, "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)

    assert auth.verify_password("admin", "atlas123") is False
