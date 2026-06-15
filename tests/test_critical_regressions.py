"""Regression tests for high-severity production safety and data integrity bugs."""

import hashlib
import json
from datetime import date, datetime

import pandas as pd
import pytest

from atlas.core import config as config_module
from atlas.core import secrets as secrets_module
from atlas.core.exceptions import ConfigurationError
from atlas.dashboard import app as dashboard_app
from atlas.dashboard import auth
from atlas.storage.database import Database, reset_database
from atlas.storage.models import DimInstrument, DimMacroSeries, DimSource
from atlas.storage.repository import FeatureRepository, MacroRepository, OHLCVRepository


def _reset_cached_state() -> None:
    config_module.get_settings.cache_clear()
    secrets_module._manager = None
    reset_database()


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch):
    for env_var in [
        "ATLAS_ENV",
        "ATLAS_DASHBOARD_USERS",
        "ATLAS_DASHBOARD__AUTH__ENABLED",
        "ATLAS_DB_CONNECTION",
        "ATLAS_KEYVAULT_URL",
    ]:
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


def test_dashboard_users_accept_valid_production_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv(
        "ATLAS_DASHBOARD_USERS",
        json.dumps({"admin": _hash_password("correct horse battery staple")}),
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


def test_dashboard_auth_cannot_be_disabled_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD__AUTH__ENABLED", "false")
    _reset_cached_state()

    with pytest.raises(ConfigurationError, match="authentication cannot be disabled"):
        dashboard_app.main()


def test_database_connection_fails_closed_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    _reset_cached_state()

    with pytest.raises(ConfigurationError, match="Database connection string must be configured"):
        Database()


def test_database_uses_local_sqlite_only_in_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "development")
    _reset_cached_state()

    assert Database()._connection_string == "sqlite:///atlas_dev.db"


def test_ohlcv_sparse_update_preserves_existing_values_and_updates_zeroes() -> None:
    db = Database("sqlite:///:memory:")
    db.create_tables()
    trade_date = date(2026, 6, 12)

    with db.session() as session:
        source = DimSource(name="tiingo", provider_type="market_data")
        instrument = DimInstrument(ticker="ABC", asset_type="equity")
        session.add_all([source, instrument])
        session.flush()

        repo = OHLCVRepository(session)
        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": trade_date,
                    "open": 10.5,
                    "high": 11.0,
                    "low": 9.5,
                    "close": 10.75,
                    "volume": 100,
                    "adj_open": 10.0,
                    "adj_high": 10.8,
                    "adj_low": 9.4,
                    "adj_close": 10.6,
                    "adj_volume": 200,
                    "dividend": 0,
                    "split_factor": 1,
                }
            ],
            source.source_id,
        )
        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": trade_date,
                    "open": 0,
                    "high": None,
                    "low": pd.NA,
                    "close": 12.0,
                    "volume": 0,
                    "adj_open": None,
                    "adj_high": None,
                    "adj_low": None,
                    "adj_close": None,
                    "adj_volume": 0,
                    "dividend": None,
                    "split_factor": None,
                }
            ],
            source.source_id,
        )

        row = repo.get_by_instrument_date(instrument.instrument_id, trade_date)
        assert row is not None
        assert float(row.open) == 0.0
        assert float(row.high) == 11.0
        assert float(row.low) == 9.5
        assert float(row.close) == 12.0
        assert row.volume == 0
        assert float(row.adj_close) == 10.6
        assert row.adj_volume == 0
        assert float(row.split_factor) == 1.0

        df = repo.get_as_dataframe([instrument.instrument_id], trade_date, trade_date)
        assert df.loc[0, "open"] == 0.0
        assert df.loc[0, "high"] == 11.0


def test_repository_dataframe_readback_preserves_zero_values() -> None:
    db = Database("sqlite:///:memory:")
    db.create_tables()
    obs_date = date(2026, 6, 12)

    with db.session() as session:
        source = DimSource(name="fred", provider_type="macro_data")
        series = DimMacroSeries(fred_id="ZERO", name="Zero Series", category="growth")
        instrument = DimInstrument(ticker="XYZ", asset_type="equity")
        session.add_all([source, series, instrument])
        session.flush()

        macro_repo = MacroRepository(session)
        macro_repo.upsert_batch(
            [{"series_id": series.series_id, "obs_date": obs_date, "value": 0}],
            source.source_id,
        )
        macro_df = macro_repo.get_as_dataframe([series.series_id], start_date=obs_date)
        assert macro_df.loc[0, "value"] == 0.0

        feature_repo = FeatureRepository(session)
        calc_timestamp = datetime(2026, 6, 12, 12, 0, 0)
        feature_repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": obs_date,
                    "feature_name": "zero_feature",
                    "source_id": source.source_id,
                    "value": 0,
                    "feature_version": "1.0.0",
                    "params_hash": "old",
                    "transform_type": "raw",
                    "calc_timestamp": calc_timestamp,
                }
            ]
        )
        feature_df = feature_repo.get_features_for_date(obs_date, ["zero_feature"])
        assert feature_df.loc[0, "zero_feature"] == 0.0


def test_feature_upsert_refreshes_lineage_metadata() -> None:
    db = Database("sqlite:///:memory:")
    db.create_tables()
    trade_date = date(2026, 6, 12)

    with db.session() as session:
        source = DimSource(name="feature_engine", provider_type="features")
        instrument = DimInstrument(ticker="XYZ", asset_type="equity")
        session.add_all([source, instrument])
        session.flush()

        repo = FeatureRepository(session)
        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": trade_date,
                    "feature_name": "momentum",
                    "source_id": source.source_id,
                    "value": 1.0,
                    "feature_version": "1.0.0",
                    "params_hash": "old",
                    "transform_type": "raw",
                    "calc_timestamp": datetime(2026, 6, 12, 8, 0, 0),
                }
            ]
        )
        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": trade_date,
                    "feature_name": "momentum",
                    "source_id": source.source_id,
                    "value": 2.0,
                    "feature_version": "2.0.0",
                    "params_hash": "new",
                    "transform_type": "zscore",
                    "calc_timestamp": datetime(2026, 6, 12, 9, 0, 0),
                }
            ]
        )

        row = repo.get_by_key(instrument.instrument_id, trade_date, "momentum")
        assert row is not None
        assert float(row.value) == 2.0
        assert row.feature_version == "2.0.0"
        assert row.params_hash == "new"
        assert row.transform_type == "zscore"
