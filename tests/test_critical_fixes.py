import json
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from atlas.core import config as config_module
from atlas.core import secrets as secrets_module
from atlas.core.exceptions import ConfigurationError
from atlas.dashboard import auth
from atlas.storage.database import Database
from atlas.storage.models import Base, DimInstrument, DimSource
from atlas.storage.repository import OHLCVRepository


@pytest.fixture(autouse=True)
def clear_cached_settings() -> None:
    config_module.get_settings.cache_clear()
    secrets_module._manager = None
    yield
    config_module.get_settings.cache_clear()
    secrets_module._manager = None


def test_dashboard_users_fail_closed_in_production_without_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)

    with pytest.raises(ConfigurationError, match="Dashboard users must be configured"):
        auth.get_users()


def test_dashboard_users_load_from_configured_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    users = {"alice": auth.hash_password("s3cret")}
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", json.dumps(users))

    assert auth.get_users() == users
    assert auth.verify_password("alice", "s3cret")
    assert not auth.verify_password("alice", "wrong")


def test_database_connection_fails_closed_in_production_without_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DB_CONNECTION", raising=False)
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)

    with pytest.raises(ConfigurationError, match="Database connection must be configured"):
        Database()


def test_ohlcv_upsert_preserves_existing_values_when_refresh_has_nulls() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    with Session() as session:
        source = DimSource(name="tiingo", provider_type="market_data")
        instrument = DimInstrument(ticker="AAPL", asset_type="equity")
        session.add_all([source, instrument])
        session.flush()

        repo = OHLCVRepository(session)
        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": date(2026, 1, 2),
                    "open": Decimal("10"),
                    "high": Decimal("12"),
                    "low": Decimal("9"),
                    "close": Decimal("11"),
                    "volume": 100,
                    "adj_close": Decimal("11"),
                }
            ],
            source.source_id,
        )

        inserted, updated = repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": date(2026, 1, 2),
                    "open": None,
                    "high": float("nan"),
                    "low": Decimal("8"),
                    "close": Decimal("0"),
                    "volume": 0,
                    "adj_close": None,
                }
            ],
            source.source_id,
        )

        assert (inserted, updated) == (0, 1)
        saved = repo.get_by_instrument_date(instrument.instrument_id, date(2026, 1, 2))
        assert saved is not None
        assert saved.open == Decimal("10.000000")
        assert saved.high == Decimal("12.000000")
        assert saved.low == Decimal("8.000000")
        assert saved.close == Decimal("0.000000")
        assert saved.volume == 0
        assert saved.adj_close == Decimal("11.000000")

        df = repo.get_as_dataframe([instrument.instrument_id])
        assert df.loc[0, "close"] == 0.0
