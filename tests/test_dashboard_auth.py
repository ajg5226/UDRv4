import hashlib

from atlas.dashboard import auth


def test_get_users_uses_defaults_in_development(monkeypatch):
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)

    monkeypatch.setattr(
        auth,
        "get_settings",
        lambda: type("Settings", (), {"environment": "development", "dashboard": type("Dashboard", (), {"auth": type("Auth", (), {"users_secret": "atlas-dashboard-users"})()})()})(),
    )
    monkeypatch.setattr(auth, "get_secret", lambda _: None)

    users = auth.get_users()

    expected_hash = hashlib.sha256("atlas123".encode()).hexdigest()
    assert users == {"admin": expected_hash, "analyst": expected_hash}


def test_get_users_fails_closed_outside_development(monkeypatch):
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)

    monkeypatch.setattr(
        auth,
        "get_settings",
        lambda: type("Settings", (), {"environment": "production", "dashboard": type("Dashboard", (), {"auth": type("Auth", (), {"users_secret": "atlas-dashboard-users"})()})()})(),
    )
    monkeypatch.setattr(auth, "get_secret", lambda _: None)

    users = auth.get_users()

    assert users == {}


def test_verify_password_rejects_default_credentials_in_production_without_config(monkeypatch):
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)

    monkeypatch.setattr(
        auth,
        "get_settings",
        lambda: type("Settings", (), {"environment": "production", "dashboard": type("Dashboard", (), {"auth": type("Auth", (), {"users_secret": "atlas-dashboard-users"})()})()})(),
    )
    monkeypatch.setattr(auth, "get_secret", lambda _: None)

    assert auth.verify_password("admin", "atlas123") is False
