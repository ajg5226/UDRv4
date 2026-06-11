import json
from datetime import date, datetime

import pandas as pd
import pytest

from atlas.core.config import reload_settings
from atlas.core.exceptions import ConfigurationError, DatabaseError, PipelineError
from atlas.dashboard import auth as dashboard_auth
from atlas.pipeline import orchestrator as orchestrator_module
from atlas.pipeline.orchestrator import PipelineOrchestrator, RunConfig
from atlas.storage import database as database_module
from atlas.storage.database import Database, reset_database
from atlas.storage.models import DimInstrument
from atlas.storage.repository import (
    FeatureRepository,
    MacroRepository,
    MacroSeriesRepository,
    OHLCVRepository,
    PipelineRunRepository,
    SourceRepository,
)


@pytest.fixture(autouse=True)
def clear_global_state(monkeypatch):
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.delenv("ATLAS_DB_CONNECTION", raising=False)
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)
    monkeypatch.setenv("ATLAS_ENV", "test")
    reload_settings()
    reset_database()
    yield
    reload_settings()
    reset_database()


def test_production_dashboard_auth_requires_configured_users(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    reload_settings()
    monkeypatch.setattr(dashboard_auth, "get_secret", lambda name: None)

    with pytest.raises(ConfigurationError):
        dashboard_auth.get_users()

    with pytest.raises(ConfigurationError):
        dashboard_auth.verify_password("admin", "atlas123")


def test_dashboard_auth_loads_configured_secret_users_in_production(monkeypatch):
    users = {"admin": dashboard_auth.hash_password("correct-horse")}

    monkeypatch.setenv("ATLAS_ENV", "production")
    reload_settings()
    monkeypatch.setattr(dashboard_auth, "get_secret", lambda name: json.dumps(users))

    assert dashboard_auth.verify_password("admin", "correct-horse")
    assert not dashboard_auth.verify_password("admin", "atlas123")


def test_production_database_connection_does_not_fall_back_to_sqlite(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    reload_settings()
    monkeypatch.setattr(database_module, "get_secret", lambda name: None)

    with pytest.raises(DatabaseError):
        Database()


def test_ohlcv_upsert_does_not_clear_existing_values_with_missing_payload():
    db = Database("sqlite:///:memory:")
    db.create_tables()
    trade_date = date(2026, 1, 2)

    with db.session() as session:
        source = SourceRepository(session).get_or_create("tiingo", "market_data")
        instrument = DimInstrument(ticker="ABC", asset_type="equity")
        session.add(instrument)
        session.flush()

        repo = OHLCVRepository(session)
        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": trade_date,
                    "open": 10,
                    "high": 12,
                    "low": 9,
                    "close": 11,
                    "volume": 100,
                    "adj_close": 11,
                }
            ],
            source.source_id,
        )

        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": trade_date,
                    "open": None,
                    "high": pd.NA,
                    "low": None,
                    "close": 13,
                    "volume": 0,
                }
            ],
            source.source_id,
        )

        row = repo.get_by_instrument_date(instrument.instrument_id, trade_date)
        assert float(row.open) == 10.0
        assert float(row.high) == 12.0
        assert float(row.low) == 9.0
        assert float(row.close) == 13.0
        assert row.volume == 0
        assert float(row.adj_close) == 11.0


def test_repository_readbacks_preserve_numeric_zero_values():
    db = Database("sqlite:///:memory:")
    db.create_tables()
    trade_date = date(2026, 1, 2)

    with db.session() as session:
        source = SourceRepository(session).get_or_create("tiingo", "market_data")
        instrument = DimInstrument(ticker="ZERO", asset_type="equity")
        session.add(instrument)
        session.flush()

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
                    "adj_open": 0,
                    "adj_high": 0,
                    "adj_low": 0,
                    "adj_close": 0,
                }
            ],
            source.source_id,
        )

        series = MacroSeriesRepository(session).get_or_create("ZERO_RATE", "Zero Rate", "rates")
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
                    "source_id": source.source_id,
                }
            ]
        )

        price_df = ohlcv_repo.get_as_dataframe([instrument.instrument_id])
        macro_df = macro_repo.get_as_dataframe([series.series_id])
        feature_df = feature_repo.get_features_for_date(trade_date)

    assert price_df.loc[0, "open"] == 0.0
    assert price_df.loc[0, "close"] == 0.0
    assert macro_df.loc[0, "value"] == 0.0
    assert feature_df.loc[0, "zero_feature"] == 0.0


def test_feature_upsert_refreshes_lineage_metadata():
    db = Database("sqlite:///:memory:")
    db.create_tables()
    trade_date = date(2026, 1, 2)
    first_calc = datetime(2026, 1, 2, 1, 0, 0)
    second_calc = datetime(2026, 1, 2, 2, 0, 0)

    with db.session() as session:
        source = SourceRepository(session).get_or_create("feature_engine", "feature")
        instrument = DimInstrument(ticker="ABC", asset_type="equity")
        session.add(instrument)
        session.flush()

        repo = FeatureRepository(session)
        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": trade_date,
                    "feature_name": "momentum",
                    "value": 1,
                    "source_id": source.source_id,
                    "feature_version": "v1",
                    "params_hash": "old",
                    "transform_type": "raw",
                    "calc_timestamp": first_calc,
                }
            ],
            run_id=1,
        )
        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": trade_date,
                    "feature_name": "momentum",
                    "value": 2,
                    "source_id": source.source_id,
                    "feature_version": "v2",
                    "params_hash": "new",
                    "transform_type": "zscore",
                    "calc_timestamp": second_calc,
                }
            ],
            run_id=2,
        )

        feature = repo.get_by_key(instrument.instrument_id, trade_date, "momentum")

    assert float(feature.value) == 2.0
    assert feature.feature_version == "v2"
    assert feature.params_hash == "new"
    assert feature.transform_type == "zscore"
    assert feature.calc_timestamp == second_calc
    assert feature.run_id == 2


@pytest.mark.asyncio
async def test_pipeline_run_creation_failure_preserves_original_error(monkeypatch):
    db = Database("sqlite:///:memory:")
    monkeypatch.setattr(orchestrator_module, "get_database", lambda: db)

    async def fake_initialize(self):
        self._initialized = True

    def raise_create_failure(self, *args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(PipelineOrchestrator, "initialize", fake_initialize)
    monkeypatch.setattr(PipelineRunRepository, "create_run", raise_create_failure)

    orchestrator = PipelineOrchestrator()

    with pytest.raises(PipelineError) as exc_info:
        await orchestrator.run(RunConfig(skip_features=True))

    assert exc_info.value.run_id is None
    assert isinstance(exc_info.value.cause, DatabaseError)
    assert isinstance(exc_info.value.cause.cause, RuntimeError)
    assert str(exc_info.value.cause.cause) == "database unavailable"
