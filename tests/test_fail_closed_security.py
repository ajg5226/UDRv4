"""Regression tests for fail-closed production safeguards."""

from types import SimpleNamespace

import pytest


def _settings(environment: str):
    """Build minimal settings object expected by tested code paths."""
    return SimpleNamespace(
        environment=environment,
        database=SimpleNamespace(connection_string_key="atlas-db-connection"),
    )


def test_database_falls_back_to_sqlite_in_development(monkeypatch: pytest.MonkeyPatch) -> None:
    """Development mode should still allow local SQLite fallback."""
    from atlas.storage import database as database_module

    monkeypatch.delenv("ATLAS_DB_CONNECTION", raising=False)
    monkeypatch.setattr(database_module, "get_settings", lambda: _settings("development"))

    db = database_module.Database()
    assert db._connection_string == "sqlite:///atlas_dev.db"


def test_database_requires_connection_string_outside_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production-like environments must not silently use local SQLite."""
    from atlas.core.exceptions import ConfigurationError
    from atlas.storage import database as database_module

    monkeypatch.delenv("ATLAS_DB_CONNECTION", raising=False)
    monkeypatch.setattr(database_module, "get_settings", lambda: _settings("production"))

    with pytest.raises(ConfigurationError) as exc_info:
        database_module.Database()

    assert "required outside development" in str(exc_info.value)


def test_dashboard_requires_explicit_users_outside_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production-like environments must not accept default credentials."""
    pytest.importorskip("streamlit")

    from atlas.core.exceptions import ConfigurationError
    from atlas.dashboard import auth as auth_module

    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth_module, "get_settings", lambda: _settings("production"))

    with pytest.raises(ConfigurationError) as exc_info:
        auth_module.get_users()

    assert "ATLAS_DASHBOARD_USERS must be configured" in str(exc_info.value)


def test_dashboard_uses_defaults_in_development(monkeypatch: pytest.MonkeyPatch) -> None:
    """Development mode can continue using bootstrap credentials."""
    pytest.importorskip("streamlit")

    from atlas.dashboard import auth as auth_module

    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth_module, "get_settings", lambda: _settings("development"))

    users = auth_module.get_users()
    assert set(users.keys()) == {"admin", "analyst"}
