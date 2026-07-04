import json

import pytest

from atlas.core import config
from atlas.core.exceptions import ConfigurationError
from atlas.dashboard import auth
from atlas.storage import database


@pytest.fixture(autouse=True)
def reset_global_state(monkeypatch: pytest.MonkeyPatch):
    for env_name in [
        "ATLAS_ENV",
        "ATLAS_DASHBOARD_USERS",
        "ATLAS_DASHBOARD__AUTH__ENABLED",
        "ATLAS_DB_CONNECTION",
        "ATLAS_KEYVAULT_URL",
    ]:
        monkeypatch.delenv(env_name, raising=False)

    config.get_settings.cache_clear()
    database.reset_database()

    yield

    config.get_settings.cache_clear()
    database.reset_database()


def test_dashboard_users_required_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    config.get_settings.cache_clear()

    with pytest.raises(ConfigurationError, match="Dashboard users must be configured"):
        auth.get_users()


def test_dashboard_users_malformed_json_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "{not-json")
    config.get_settings.cache_clear()

    with pytest.raises(ConfigurationError, match="valid JSON"):
        auth.get_users()


def test_dashboard_uses_configured_production_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    password_hash = auth.hash_password("s3cret")
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", json.dumps({"ops": password_hash}))
    config.get_settings.cache_clear()

    assert auth.verify_password("ops", "s3cret")
    assert not auth.verify_password("admin", "atlas123")


def test_dashboard_auth_cannot_be_disabled_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = config.Settings(
        ATLAS_ENV="production",
        dashboard=config.DashboardConfig(
            auth=config.DashboardAuthConfig(enabled=False),
        ),
    )
    monkeypatch.setattr(auth, "get_settings", lambda: settings)

    with pytest.raises(ConfigurationError, match="cannot be disabled"):
        auth.validate_dashboard_auth_config()


def test_login_default_credential_hint_is_development_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    config.get_settings.cache_clear()
    assert not auth.should_show_development_hint()

    monkeypatch.setenv("ATLAS_ENV", "development")
    config.get_settings.cache_clear()
    assert auth.should_show_development_hint()


def test_database_connection_required_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    config.get_settings.cache_clear()

    with pytest.raises(ConfigurationError, match="Database connection string is required"):
        database.Database()
