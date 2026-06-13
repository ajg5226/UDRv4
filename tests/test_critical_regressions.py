import json
from contextlib import contextmanager
from datetime import date, datetime

import pandas as pd
import pytest

import atlas.core.secrets as secrets
from atlas.core.config import reload_settings
from atlas.core.exceptions import ConfigurationError, DatabaseError, PipelineError
from atlas.dashboard.auth import get_users, hash_password, verify_password
from atlas.pipeline.orchestrator import PipelineOrchestrator, RunConfig
from atlas.storage.database import Database, reset_database
from atlas.storage.models import DimInstrument, DimMacroSeries, DimSource
from atlas.storage.repository import FeatureRepository, MacroRepository, OHLCVRepository
from scripts.backfill_5year import _extract_row_date


@pytest.fixture(autouse=True)
def reset_global_state(monkeypatch):
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.delenv("ATLAS_DB_CONNECTION", raising=False)
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)
    secrets._manager = None
    reload_settings()
    reset_database()
    yield
    secrets._manager = None
    reload_settings()
    reset_database()


def test_dashboard_auth_fails_closed_without_production_users(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    reload_settings()

    with pytest.raises(ConfigurationError):
        get_users()


def test_dashboard_auth_uses_configured_users_in_production(monkeypatch):
    password_hash = hash_password("correct horse battery staple")
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", json.dumps({"alice": password_hash}))
    reload_settings()

    assert verify_password("alice", "correct horse battery staple") is True
    assert verify_password("admin", "atlas123") is False


def test_database_fails_closed_without_production_connection(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    reload_settings()

    with pytest.raises(DatabaseError):
        Database()


def test_database_allows_sqlite_fallback_in_development(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "development")
    reload_settings()

    db = Database()

    assert db._connection_string == "sqlite:///atlas_dev.db"


def _seed_dimensions(session):
    source = DimSource(name="test", provider_type="test", base_url="https://example.test")
    instrument = DimInstrument(ticker="ABC", asset_type="equity")
    series = DimMacroSeries(fred_id="ZERO", name="Zero Series", category="test")
    session.add_all([source, instrument, series])
    session.flush()
    return source, instrument, series


def test_ohlcv_update_preserves_existing_values_when_provider_payload_is_missing():
    db = Database("sqlite:///:memory:")
    db.create_tables()
    trade_date = date(2026, 1, 2)

    with db.session() as session:
        source, instrument, _ = _seed_dimensions(session)
        repo = OHLCVRepository(session)
        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": trade_date,
                    "open": 10,
                    "high": 11,
                    "low": 9,
                    "close": 10.5,
                    "volume": 100,
                    "adj_open": 10,
                    "adj_high": 11,
                    "adj_low": 9,
                    "adj_close": 10.5,
                    "adj_volume": 100,
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
                    "high": float("nan"),
                    "low": None,
                    "close": None,
                    "volume": None,
                }
            ],
            source.source_id,
        )

        record = repo.get_by_instrument_date(instrument.instrument_id, trade_date)

        assert float(record.open) == 0.0
        assert float(record.high) == 11.0
        assert float(record.low) == 9.0
        assert float(record.close) == 10.5
        assert record.volume == 100


def test_repository_dataframes_preserve_legitimate_zero_values():
    db = Database("sqlite:///:memory:")
    db.create_tables()
    trade_date = date(2026, 1, 2)

    with db.session() as session:
        source, instrument, series = _seed_dimensions(session)

        ohlcv_repo = OHLCVRepository(session)
        ohlcv_repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": trade_date,
                    "open": 0,
                    "high": 0,
                    "low": 0,
                    "close": 0,
                }
            ],
            source.source_id,
        )

        macro_repo = MacroRepository(session)
        macro_repo.upsert_batch(
            [{"series_id": series.series_id, "obs_date": trade_date, "value": 0}],
            source.source_id,
        )

        feature_repo = FeatureRepository(session)
        feature_repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": trade_date,
                    "feature_name": "zero_feature",
                    "value": 0,
                }
            ]
        )

        ohlcv_df = ohlcv_repo.get_as_dataframe()
        macro_df = macro_repo.get_as_dataframe()
        feature_df = feature_repo.get_features_for_date(trade_date)

        assert ohlcv_df.loc[0, "open"] == 0.0
        assert macro_df.loc[0, "value"] == 0.0
        assert feature_df.loc[0, "zero_feature"] == 0.0


def test_feature_upsert_refreshes_lineage_metadata():
    db = Database("sqlite:///:memory:")
    db.create_tables()
    trade_date = date(2026, 1, 2)
    old_timestamp = datetime(2026, 1, 2, 10, 0)
    new_timestamp = datetime(2026, 1, 2, 11, 0)

    with db.session() as session:
        _, instrument, _ = _seed_dimensions(session)
        repo = FeatureRepository(session)
        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": trade_date,
                    "feature_name": "momentum_zscore",
                    "value": 1.0,
                    "feature_version": "1.0.0",
                    "params_hash": "old",
                    "transform_type": "raw",
                    "calc_timestamp": old_timestamp,
                }
            ]
        )

        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": trade_date,
                    "feature_name": "momentum_zscore",
                    "value": 2.0,
                    "feature_version": "2.0.0",
                    "params_hash": "new",
                    "transform_type": "zscore",
                    "calc_timestamp": new_timestamp,
                }
            ],
            run_id=42,
        )

        record = repo.get_by_key(instrument.instrument_id, trade_date, "momentum_zscore")

        assert float(record.value) == 2.0
        assert record.feature_version == "2.0.0"
        assert record.params_hash == "new"
        assert record.transform_type == "zscore"
        assert record.calc_timestamp == new_timestamp
        assert record.run_id == 42


def test_backfill_extracts_fred_observation_date_column():
    row = pd.Series({"obs_date": pd.Timestamp("2026-01-02"), "value": 0.0})

    assert _extract_row_date(row, "obs_date") == date(2026, 1, 2)


class FailingDatabase:
    @contextmanager
    def session(self):
        raise RuntimeError("create run failed")
        yield


@pytest.mark.asyncio
async def test_pipeline_preserves_original_error_when_run_creation_fails():
    orchestrator = object.__new__(PipelineOrchestrator)
    orchestrator._initialized = True
    orchestrator._db = FailingDatabase()

    with pytest.raises(PipelineError) as exc_info:
        await orchestrator.run(RunConfig(skip_features=True))

    assert exc_info.value.run_id is None
    assert isinstance(exc_info.value.cause, RuntimeError)
    assert str(exc_info.value.cause) == "create run failed"
