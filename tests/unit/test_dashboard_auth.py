"""Tests for dashboard authentication credential loading."""

import hashlib
import importlib
import sys
import types

import pytest


def _load_auth_module(monkeypatch: pytest.MonkeyPatch):
    """Load auth module with a lightweight streamlit stub."""
    streamlit_stub = types.SimpleNamespace(session_state={})
    monkeypatch.setitem(sys.modules, "streamlit", streamlit_stub)
    sys.modules.pop("atlas.dashboard.auth", None)

    import atlas.dashboard.auth as auth

    return importlib.reload(auth)


def test_get_users_fails_closed_in_production_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Production must not fall back to hardcoded credentials."""
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    auth = _load_auth_module(monkeypatch)

    with pytest.raises(RuntimeError, match="Dashboard credentials are not configured"):
        auth.get_users()


def test_get_users_fails_closed_in_production_on_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Production should reject malformed credential payloads."""
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "{invalid-json")
    auth = _load_auth_module(monkeypatch)

    with pytest.raises(RuntimeError, match="must be valid JSON"):
        auth.get_users()


def test_get_users_returns_development_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Development keeps local defaults for convenience."""
    monkeypatch.setenv("ATLAS_ENV", "development")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    auth = _load_auth_module(monkeypatch)

    users = auth.get_users()
    expected_hash = hashlib.sha256("atlas123".encode()).hexdigest()

    assert users == {"admin": expected_hash, "analyst": expected_hash}

