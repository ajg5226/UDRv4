"""Security-focused tests for dashboard authentication behavior."""

import json
import sys
from types import SimpleNamespace

# The auth module imports Streamlit at module load; tests below only
# exercise credential helpers, so a minimal stub is sufficient.
sys.modules.setdefault("streamlit", SimpleNamespace(session_state={}))

from atlas.dashboard import auth


def _settings(environment: str) -> SimpleNamespace:
    """Create a lightweight settings object used by auth helpers."""
    return SimpleNamespace(
        environment=environment,
        dashboard=SimpleNamespace(
            auth=SimpleNamespace(users_secret="atlas-dashboard-users")
        ),
    )


def test_production_without_credentials_fails_closed(monkeypatch) -> None:
    """Production must not accept hardcoded fallback credentials."""
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.setattr(auth, "get_secret", lambda _name: None)
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)

    assert auth.get_users() == {}
    assert auth.verify_password("admin", "atlas123") is False


def test_production_uses_secret_credentials(monkeypatch) -> None:
    """Production should authenticate when secret-backed users are present."""
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("production"))
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(
        auth,
        "get_secret",
        lambda _name: json.dumps({"ops": auth.hash_password("S3cur3!")}),
    )

    assert auth.verify_password("ops", "S3cur3!") is True


def test_development_keeps_local_defaults(monkeypatch) -> None:
    """Development keeps convenience defaults for local usage."""
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("development"))
    monkeypatch.setattr(auth, "get_secret", lambda _name: None)
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)

    assert auth.verify_password("admin", "atlas123") is True
