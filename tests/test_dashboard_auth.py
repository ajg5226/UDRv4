from types import SimpleNamespace

import atlas.dashboard.auth as auth


def _make_settings(environment: str, users_secret: str = "atlas-dashboard-users") -> SimpleNamespace:
    return SimpleNamespace(
        environment=environment,
        dashboard=SimpleNamespace(auth=SimpleNamespace(users_secret=users_secret)),
    )


def test_get_users_fails_closed_in_production_when_secret_missing(monkeypatch) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: _make_settings("production"))
    monkeypatch.setattr(auth, "get_secret", lambda _name: None)

    users = auth.get_users()

    assert users == {}
    assert not auth.verify_password("admin", "atlas123")


def test_get_users_fails_closed_in_production_when_secret_invalid_json(monkeypatch) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: _make_settings("production"))
    monkeypatch.setattr(auth, "get_secret", lambda _name: "{not-json")

    users = auth.get_users()

    assert users == {}
    assert not auth.verify_password("admin", "atlas123")


def test_get_users_uses_default_credentials_only_in_development(monkeypatch) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: _make_settings("development"))
    monkeypatch.setattr(auth, "get_secret", lambda _name: None)

    users = auth.get_users()

    assert "admin" in users
    assert auth.verify_password("admin", "atlas123")


def test_get_users_honors_secret_credentials(monkeypatch) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: _make_settings("production"))
    monkeypatch.setattr(
        auth,
        "get_secret",
        lambda _name: '{"ops":"43f8a2ad1880e4f404877b911b5a8335f72f8500f595133fe9c000f448ca28b1"}',
    )

    users = auth.get_users()

    assert "ops" in users
    assert auth.verify_password("ops", "atlas123")
