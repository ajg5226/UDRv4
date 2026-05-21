"""Regression tests for dashboard authentication safety."""

import json

import pytest

from atlas.core import secrets as secrets_module
from atlas.core.config import get_settings
from atlas.core.exceptions import ConfigurationError
from atlas.dashboard import auth


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch):
    """Clear cached configuration and secret manager state around each test."""
    for env_var in (
        "ATLAS_ENV",
        "ATLAS_DASHBOARD_USERS",
        "ATLAS_KEYVAULT_URL",
        "ATLAS_DASHBOARD__AUTH__ENABLED",
    ):
        monkeypatch.delenv(env_var, raising=False)
    get_settings.cache_clear()
    monkeypatch.setattr(secrets_module, "_manager", None)
    yield
    get_settings.cache_clear()


def test_development_uses_default_dashboard_credentials() -> None:
    users = auth.get_users()

    assert auth.hash_password("atlas123") == users["admin"]
    assert auth.hash_password("atlas123") == users["analyst"]


def test_dashboard_credentials_load_from_configured_secret(monkeypatch) -> None:
    expected_hash = auth.hash_password("strong-password")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", json.dumps({"admin": expected_hash}))

    assert auth.get_users() == {"admin": expected_hash}


def test_production_requires_dashboard_credentials(monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError, match="required outside development"):
        auth.get_users()


def test_production_rejects_malformed_dashboard_credentials(monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "not-json")
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError, match="malformed"):
        auth.get_users()


def test_login_page_hides_development_credentials_in_production(monkeypatch) -> None:
    expected_hash = auth.hash_password("strong-password")
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", json.dumps({"admin": expected_hash}))
    get_settings.cache_clear()
    fake_streamlit = FakeStreamlit()
    monkeypatch.setattr(auth, "st", fake_streamlit)

    auth.show_login()

    rendered_markdown = "\n".join(fake_streamlit.markdown_calls)
    assert "atlas123" not in rendered_markdown
    assert "Default credentials" not in rendered_markdown


def test_login_page_shows_development_credentials_only_in_development(monkeypatch) -> None:
    fake_streamlit = FakeStreamlit()
    monkeypatch.setattr(auth, "st", fake_streamlit)

    auth.show_login()

    rendered_markdown = "\n".join(fake_streamlit.markdown_calls)
    assert "atlas123" in rendered_markdown
    assert "Default credentials" in rendered_markdown


class FakeForm:
    """Minimal Streamlit form double for rendering login tests."""

    def __enter__(self) -> "FakeForm":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None


class FakeStreamlit:
    """Minimal Streamlit double used by show_login."""

    def __init__(self) -> None:
        self.markdown_calls: list[str] = []
        self.session_state: dict[str, str | bool] = {}

    def title(self, text: str) -> None:
        pass

    def markdown(self, text: str) -> None:
        self.markdown_calls.append(text)

    def form(self, key: str) -> FakeForm:
        return FakeForm()

    def text_input(self, label: str, type: str | None = None) -> str:
        return ""

    def form_submit_button(self, label: str) -> bool:
        return False

    def success(self, text: str) -> None:
        pass

    def error(self, text: str) -> None:
        pass

    def rerun(self) -> None:
        pass
