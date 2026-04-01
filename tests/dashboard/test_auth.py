import hashlib

from atlas.dashboard.auth import verify_password
from atlas.core.config import get_settings


def _password_hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def test_production_rejects_default_fallback_credentials(monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    get_settings.cache_clear()

    assert verify_password("admin", "atlas123") is False

    get_settings.cache_clear()


def test_production_accepts_explicit_credentials(monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv(
        "ATLAS_DASHBOARD_USERS",
        '{"admin":"' + _password_hash("correct-password") + '"}',
    )
    get_settings.cache_clear()

    assert verify_password("admin", "correct-password") is True
    assert verify_password("admin", "wrong-password") is False

    get_settings.cache_clear()
