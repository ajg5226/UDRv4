import json
import sys
import types

import pytest

from atlas.core.config import get_settings


class _Form:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _streamlit_stub():
    stub = types.ModuleType("streamlit")
    stub.markdown_calls = []
    stub.session_state = {}
    stub.title = lambda _text: None
    stub.markdown = lambda text: stub.markdown_calls.append(text)
    stub.form = lambda _name: _Form()
    stub.text_input = lambda *_args, **_kwargs: ""
    stub.form_submit_button = lambda _label: False
    stub.success = lambda _text: None
    stub.error = lambda _text: None
    stub.rerun = lambda: None
    return stub


@pytest.fixture
def auth_module(monkeypatch):
    monkeypatch.setitem(sys.modules, "streamlit", _streamlit_stub())
    sys.modules.pop("atlas.dashboard.auth", None)
    get_settings.cache_clear()

    import atlas.dashboard.auth as auth

    yield auth

    get_settings.cache_clear()
    sys.modules.pop("atlas.dashboard.auth", None)


def test_development_uses_default_credentials(auth_module, monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "development")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    get_settings.cache_clear()

    assert auth_module.verify_password("admin", "atlas123") is True


def test_production_requires_configured_dashboard_users(auth_module, monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth_module, "get_secret", lambda _name: None)
    get_settings.cache_clear()

    with pytest.raises(auth_module.AuthConfigurationError):
        auth_module.get_users()


def test_production_loads_dashboard_users_from_configured_secret(auth_module, monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    get_settings.cache_clear()

    password_hash = auth_module.hash_password("correct-horse")
    monkeypatch.setattr(
        auth_module,
        "get_secret",
        lambda name: json.dumps({"alice": password_hash})
        if name == "atlas-dashboard-users"
        else None,
    )

    assert auth_module.verify_password("alice", "correct-horse") is True
    assert auth_module.verify_password("alice", "wrong") is False


def test_malformed_dashboard_users_does_not_fall_back_to_defaults(auth_module, monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "{not-json")
    get_settings.cache_clear()

    with pytest.raises(auth_module.AuthConfigurationError):
        auth_module.get_users()


def test_login_hint_only_renders_in_development(auth_module, monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    get_settings.cache_clear()

    auth_module.show_login()

    assert all("Default credentials" not in call for call in auth_module.st.markdown_calls)

    monkeypatch.setenv("ATLAS_ENV", "development")
    get_settings.cache_clear()
    auth_module.st.markdown_calls.clear()

    auth_module.show_login()

    assert any("Default credentials" in call for call in auth_module.st.markdown_calls)


def test_production_dashboard_auth_cannot_be_disabled(auth_module, monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD__AUTH__ENABLED", "false")
    get_settings.cache_clear()

    with pytest.raises(auth_module.AuthConfigurationError):
        auth_module.validate_auth_settings()
