import hashlib
import json
from contextlib import contextmanager
from datetime import date, datetime

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import atlas.core.secrets as secrets_module
from atlas.core.config import get_settings
from atlas.core.exceptions import ConfigurationError, PipelineError
from atlas.dashboard.auth import get_users, verify_password
from atlas.pipeline.orchestrator import PipelineOrchestrator, RunConfig
from atlas.storage.database import Database, reset_database
from atlas.storage.models import Base, DimInstrument, DimMacroSeries, DimSource
from atlas.storage.repository import FeatureRepository, MacroRepository, OHLCVRepository
from scripts.backfill_5year import get_provider_row_date


@pytest.fixture(autouse=True)
def reset_global_state(monkeypatch):
    reset_database()
    get_settings.cache_clear()
    secrets_module._manager = None
    for name in (
        "ATLAS_ENV",
        "ATLAS_DB_CONNECTION",
        "ATLAS_DASHBOARD_USERS",
        "ATLAS_KEYVAULT_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    yield
    reset_database()
    get_settings.cache_clear()
    secrets_module._manager = None


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_dashboard_users_fail_closed_in_production(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError, match="Dashboard users secret is required"):
        get_users()

    password_hash = hashlib.sha256(b"correct horse battery staple").hexdigest()
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", json.dumps({"admin": password_hash}))

    assert get_users() == {"admin": password_hash}
    assert verify_password("admin", "correct horse battery staple") is True
    assert verify_password("admin", "atlas123") is False


def test_dashboard_users_reject_malformed_production_secret(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "{not-json")
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError, match="not valid JSON"):
        get_users()


def test_database_connection_fails_closed_in_production(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError, match="Database connection string is required"):
        Database()


def test_ohlcv_sparse_update_preserves_existing_values_and_reads_zero(db_session):
    source = DimSource(name="tiingo", provider_type="market_data")
    instrument = DimInstrument(ticker="ZERO", asset_type="equity")
    db_session.add_all([source, instrument])
    db_session.flush()

    repo = OHLCVRepository(db_session)
    trade_date = date(2026, 1, 2)
    repo.upsert_batch(
        [
            {
                "instrument_id": instrument.instrument_id,
                "trade_date": trade_date,
                "open": 100.0,
                "high": 110.0,
                "low": 90.0,
                "close": 105.0,
                "volume": 123,
                "adj_close": 105.0,
            }
        ],
        source_id=source.source_id,
    )

    inserted, updated = repo.upsert_batch(
        [
            {
                "instrument_id": instrument.instrument_id,
                "trade_date": trade_date,
                "open": None,
                "high": None,
                "low": None,
                "close": 0.0,
                "volume": 0,
                "adj_close": None,
            }
        ],
        source_id=source.source_id,
    )

    row = repo.get_by_instrument_date(instrument.instrument_id, trade_date)
    df = repo.get_as_dataframe([instrument.instrument_id], trade_date, trade_date)

    assert (inserted, updated) == (0, 1)
    assert float(row.open) == 100.0
    assert float(row.high) == 110.0
    assert float(row.low) == 90.0
    assert float(row.close) == 0.0
    assert row.volume == 0
    assert float(row.adj_close) == 105.0
    assert df.iloc[0]["open"] == 100.0
    assert df.iloc[0]["close"] == 0.0


def test_macro_and_feature_zero_readback_and_feature_lineage_refresh(db_session):
    source = DimSource(name="fred", provider_type="macro_data")
    instrument = DimInstrument(ticker="ABC", asset_type="equity")
    series = DimMacroSeries(fred_id="TEST", name="Test Series", category="growth")
    db_session.add_all([source, instrument, series])
    db_session.flush()

    macro_repo = MacroRepository(db_session)
    macro_repo.upsert_batch(
        [
            {
                "series_id": series.series_id,
                "obs_date": date(2026, 1, 2),
                "value": 0.0,
            }
        ],
        source_id=source.source_id,
    )

    macro_df = macro_repo.get_as_dataframe([series.series_id])
    assert macro_df.iloc[0]["value"] == 0.0

    feature_repo = FeatureRepository(db_session)
    feature_date = date(2026, 1, 2)
    feature_repo.upsert_batch(
        [
            {
                "instrument_id": instrument.instrument_id,
                "trade_date": feature_date,
                "feature_name": "daily_return",
                "source_id": source.source_id,
                "value": 1.5,
                "feature_version": "v1",
                "params_hash": "old",
                "transform_type": "raw",
                "calc_timestamp": datetime(2026, 1, 2, 12),
            }
        ],
        run_id=1,
    )
    feature_repo.upsert_batch(
        [
            {
                "instrument_id": instrument.instrument_id,
                "trade_date": feature_date,
                "feature_name": "daily_return",
                "source_id": source.source_id,
                "value": 0.0,
                "feature_version": "v2",
                "params_hash": "new",
                "transform_type": "zscore",
                "calc_timestamp": datetime(2026, 1, 2, 13),
            }
        ],
        run_id=2,
    )

    feature = feature_repo.get_by_key(instrument.instrument_id, feature_date, "daily_return")
    feature_df = feature_repo.get_features_for_date(feature_date)

    assert float(feature.value) == 0.0
    assert feature.feature_version == "v2"
    assert feature.params_hash == "new"
    assert feature.transform_type == "zscore"
    assert feature.run_id == 2
    assert feature_df.iloc[0]["daily_return"] == 0.0


def test_backfill_uses_fred_obs_date_key():
    row = pd.Series({"obs_date": "2026-01-02", "value": 1.25})

    assert get_provider_row_date(row, "obs_date") == date(2026, 1, 2)


@pytest.mark.asyncio()
async def test_pipeline_early_run_creation_failure_preserves_original_cause():
    original = RuntimeError("create run failed")

    class FailingSession:
        def __enter__(self):
            raise original

        def __exit__(self, exc_type, exc, traceback):
            return False

    class FailingDatabase:
        @contextmanager
        def session(self):
            with FailingSession():
                yield

    orchestrator = PipelineOrchestrator.__new__(PipelineOrchestrator)
    orchestrator._initialized = True
    orchestrator._db = FailingDatabase()

    with pytest.raises(PipelineError) as exc_info:
        await orchestrator.run(RunConfig(skip_features=True))

    assert exc_info.value.run_id is None
    assert exc_info.value.cause is original
