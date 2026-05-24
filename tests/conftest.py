"""Shared pytest configuration for ATLAS tests."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture(autouse=True)
def reset_global_state():
    """Keep cached settings, secrets, and database handles isolated per test."""
    import atlas.core.secrets as secrets
    from atlas.core.config import get_settings
    from atlas.storage.database import reset_database

    get_settings.cache_clear()
    secrets._manager = None
    reset_database()

    yield

    get_settings.cache_clear()
    secrets._manager = None
    reset_database()
