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


def test_verify_password_fails_closed_in_non_development_when_missing_credentials(
    monkeypatch,
) -> None:
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr(auth, "get_secret", lambda _: None)

    assert auth.verify_password("admin", "atlas123") is False


def test_verify_password_fails_closed_in_non_development_on_invalid_credentials_json(
    monkeypatch,
) -> None:
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr(auth, "get_secret", lambda _: "{not-json")

    assert auth.verify_password("admin", "atlas123") is False


def test_verify_password_uses_secret_credentials_in_non_development(monkeypatch) -> None:
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))

    credential_payload = {"admin": auth.hash_password("correct-horse-battery-staple")}
    monkeypatch.setattr(auth, "get_secret", lambda _: json.dumps(credential_payload))

    assert auth.verify_password("admin", "correct-horse-battery-staple") is True
    assert auth.verify_password("admin", "atlas123") is False


def test_verify_password_preserves_default_credentials_in_development(monkeypatch) -> None:
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("development"))
    monkeypatch.setattr(auth, "get_secret", lambda _: None)

    assert auth.verify_password("admin", "atlas123") is True
