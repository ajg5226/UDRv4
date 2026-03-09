"""Tests for dashboard authentication behavior."""

import hashlib
import importlib
import json
import sys
import types
from pathlib import Path


SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


def _load_auth_module():
    """Import auth module with a lightweight streamlit stub."""
    sys.modules.setdefault("streamlit", types.SimpleNamespace(session_state={}))
    return importlib.import_module("atlas.dashboard.auth")


def test_production_requires_explicit_users(monkeypatch):
    """Production should fail closed when users are not configured."""
    auth = _load_auth_module()
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(
        auth,
        "get_settings",
        lambda: types.SimpleNamespace(environment="production"),
    )

    assert auth.get_users() == {}
    assert auth.verify_password("admin", "atlas123") is False


def test_development_uses_default_credentials(monkeypatch):
    """Development should keep convenient default credentials."""
    auth = _load_auth_module()
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(
        auth,
        "get_settings",
        lambda: types.SimpleNamespace(environment="development"),
    )

    users = auth.get_users()
    expected_hash = hashlib.sha256("atlas123".encode()).hexdigest()
    assert users["admin"] == expected_hash
    assert users["analyst"] == expected_hash
    assert auth.verify_password("admin", "atlas123") is True


def test_production_uses_configured_hashes(monkeypatch):
    """Production should honor configured user hashes."""
    auth = _load_auth_module()
    configured = {
        "ops": hashlib.sha256("strongpass".encode()).hexdigest(),
    }
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", json.dumps(configured))
    monkeypatch.setattr(
        auth,
        "get_settings",
        lambda: types.SimpleNamespace(environment="production"),
    )

    assert auth.get_users() == configured
    assert auth.verify_password("ops", "strongpass") is True


def test_production_malformed_user_config_fails_closed(monkeypatch):
    """Malformed user JSON must not re-enable default credentials."""
    auth = _load_auth_module()
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "{not-json}")
    monkeypatch.setattr(
        auth,
        "get_settings",
        lambda: types.SimpleNamespace(environment="production"),
    )

    assert auth.get_users() == {}
    assert auth.verify_password("admin", "atlas123") is False
