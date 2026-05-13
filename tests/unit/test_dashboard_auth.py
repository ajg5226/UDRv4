import importlib
import json
import sys
import types


def _clear_settings_cache() -> None:
    from atlas.core.config import get_settings

    get_settings.cache_clear()


def _load_auth_module(monkeypatch):
    streamlit_stub = types.SimpleNamespace(session_state={})
    monkeypatch.setitem(sys.modules, "streamlit", streamlit_stub)

    import atlas.dashboard.auth as auth

    return importlib.reload(auth)


def test_production_auth_fails_closed_without_configured_users(monkeypatch):
    auth = _load_auth_module(monkeypatch)
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_secret", lambda name: None)
    _clear_settings_cache()

    assert auth.get_users() == {}
    assert not auth.verify_password("admin", "atlas123")


def test_production_auth_fails_closed_on_malformed_users_json(monkeypatch):
    auth = _load_auth_module(monkeypatch)
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "{not-json")
    _clear_settings_cache()

    assert auth.get_users() == {}
    assert not auth.verify_password("admin", "atlas123")


def test_production_auth_loads_configured_users_secret(monkeypatch):
    auth = _load_auth_module(monkeypatch)
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    users = {"analyst": auth.hash_password("correct-horse")}
    calls: list[str] = []

    def fake_get_secret(name: str) -> str:
        calls.append(name)
        return json.dumps(users)

    monkeypatch.setattr(auth, "get_secret", fake_get_secret)
    _clear_settings_cache()

    assert auth.verify_password("analyst", "correct-horse")
    assert not auth.verify_password("analyst", "wrong-password")
    assert calls
    assert set(calls) == {"atlas-dashboard-users"}


def test_development_auth_keeps_local_default_users(monkeypatch):
    auth = _load_auth_module(monkeypatch)
    monkeypatch.setenv("ATLAS_ENV", "development")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_secret", lambda name: None)
    _clear_settings_cache()

    assert auth.verify_password("admin", "atlas123")
    assert auth.verify_password("analyst", "atlas123")
