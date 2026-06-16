"""Regression tests for dashboard authentication safety."""

import hashlib
import json
from types import SimpleNamespace

import pytest

from atlas.core import config as config_module
from atlas.core import secrets as secrets_module
from atlas.core.exceptions import ConfigurationError
from atlas.dashboard import auth


def _reset_cached_state() -> None:
    config_module.get_settings.cache_clear()
    secrets_module._manager = None


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch):
    for env_var in ["ATLAS_ENV", "ATLAS_DASHBOARD_USERS", "ATLAS_KEYVAULT_URL"]:
        monkeypatch.delenv(env_var, raising=False)
    _reset_cached_state()
    yield
    _reset_cached_state()


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def test_dashboard_users_fail_closed_without_production_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    _reset_cached_state()

    with pytest.raises(ConfigurationError, match="Dashboard users must be configured"):
        auth.get_users()


def test_dashboard_users_reject_malformed_production_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "{not-json")
    _reset_cached_state()

    with pytest.raises(ConfigurationError, match="not valid JSON"):
        auth.get_users()


def test_dashboard_users_accept_configured_secret_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setattr(
        auth,
        "get_secret",
        lambda name: json.dumps({"admin": _hash_password("correct horse battery staple")}),
    )
    _reset_cached_state()

    assert auth.verify_password("admin", "correct horse battery staple") is True
    assert auth.verify_password("admin", "atlas123") is False


def test_development_dashboard_defaults_remain_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "development")
    _reset_cached_state()

    assert auth.verify_password("admin", "atlas123") is True


class _FakeForm:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        return False


class _FakeStreamlit:
    def __init__(self) -> None:
        self.markdown_calls: list[str] = []
        self.session_state: dict[str, str] = {}

    def title(self, value: str) -> None:
        pass

    def markdown(self, value: str) -> None:
        self.markdown_calls.append(value)

    def form(self, name: str) -> _FakeForm:
        return _FakeForm()

    def text_input(self, label: str, type: str | None = None) -> str:
        return ""

    def form_submit_button(self, label: str) -> bool:
        return False

    def success(self, value: str) -> None:
        pass

    def error(self, value: str) -> None:
        pass

    def rerun(self) -> None:
        pass


def test_production_login_does_not_disclose_development_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_streamlit = _FakeStreamlit()
    monkeypatch.setattr(auth, "st", fake_streamlit)
    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(environment="production"))

    auth.show_login()

    rendered_markdown = "\n".join(fake_streamlit.markdown_calls)
    assert "atlas123" not in rendered_markdown
    assert "Default credentials" not in rendered_markdown
