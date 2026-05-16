"""Regression tests for dashboard authentication configuration."""

from types import SimpleNamespace

from atlas.dashboard import auth


def _settings(environment: str = "production") -> SimpleNamespace:
    return SimpleNamespace(
        environment=environment,
        dashboard=SimpleNamespace(
            auth=SimpleNamespace(users_secret="atlas-dashboard-users"),
        ),
    )


def test_configured_secret_users_are_loaded(monkeypatch) -> None:
    password_hash = auth.hash_password("s3cret")
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr(
        auth,
        "get_secret",
        lambda name: f'{{"admin": "{password_hash}"}}',
    )

    assert auth.get_users() == {"admin": password_hash}
    assert auth.verify_password("admin", "s3cret") is True
    assert auth.verify_password("admin", "atlas123") is False


def test_production_without_configured_users_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr(auth, "get_secret", lambda name: None)

    assert auth.get_users() == {}
    assert auth.verify_password("admin", "atlas123") is False


def test_malformed_production_users_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr(auth, "get_secret", lambda name: "{not json")

    assert auth.get_users() == {}
    assert auth.verify_password("admin", "atlas123") is False


def test_development_without_configured_users_allows_defaults(monkeypatch) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("development"))
    monkeypatch.setattr(auth, "get_secret", lambda name: None)

    assert auth.verify_password("admin", "atlas123") is True
    assert auth.verify_password("analyst", "atlas123") is True
