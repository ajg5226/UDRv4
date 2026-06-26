"""Regression coverage for critical fail-closed and data-integrity paths."""

import json
from contextlib import contextmanager
from datetime import date

import pandas as pd
import pytest

from atlas.core.config import get_settings
from atlas.core.exceptions import ConfigurationError, DatabaseError, PipelineError
from atlas.dashboard import auth
from atlas.pipeline.orchestrator import PipelineOrchestrator, RunConfig
from atlas.storage.database import Database
from atlas.storage.models import DimInstrument, DimMacroSeries
from atlas.storage.repository import (
    FeatureRepository,
    InstrumentRepository,
    MacroRepository,
    MacroSeriesRepository,
    OHLCVRepository,
    SourceRepository,
)


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Keep environment-specific settings isolated across tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_production_database_requires_configured_connection(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DB_CONNECTION", raising=False)
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)

    with pytest.raises(DatabaseError) as exc_info:
        Database()

    assert "required outside development" in str(exc_info.value)


def test_dashboard_auth_requires_users_outside_development(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_secret", lambda name: None)

    with pytest.raises(ConfigurationError) as exc_info:
        auth.get_users()

    assert "required outside development" in str(exc_info.value)


def test_dashboard_auth_uses_configured_secret_in_production(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    users = {"ops": auth.hash_password("correct-horse")}
    monkeypatch.setattr(auth, "get_secret", lambda name: json.dumps(users))

    assert auth.verify_password("ops", "correct-horse")
    assert not auth.verify_password("admin", "atlas123")


def test_ohlcv_sparse_update_preserves_existing_values_and_accepts_zero():
    db = Database("sqlite:///:memory:")
    db.create_tables()
    trade_date = date(2026, 1, 2)

    with db.session() as session:
        source = SourceRepository(session).get_or_create("tiingo", "market")
        instrument = InstrumentRepository(session).add(
            DimInstrument(ticker="AAPL", asset_type="equity")
        )
        repo = OHLCVRepository(session)

        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": trade_date,
                    "open": 10.0,
                    "high": 12.0,
                    "low": 9.0,
                    "close": 11.0,
                    "volume": 100,
                    "adj_open": 10.1,
                    "adj_high": 12.1,
                    "adj_low": 9.1,
                    "adj_close": 11.1,
                    "adj_volume": 101,
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
                    "high": 0.0,
                    "low": pd.NA,
                    "close": float("nan"),
                    "volume": None,
                    "adj_close": None,
                    "adj_volume": 0,
                }
            ],
            source.source_id,
        )

        stored = repo.get_by_instrument_date(instrument.instrument_id, trade_date)
        assert stored is not None
        assert float(stored.open) == 10.0
        assert float(stored.high) == 0.0
        assert float(stored.low) == 9.0
        assert float(stored.close) == 11.0
        assert stored.volume == 100
        assert float(stored.adj_close) == 11.1
        assert stored.adj_volume == 0

        df = repo.get_as_dataframe([instrument.instrument_id])
        assert df.loc[0, "high"] == 0.0


def test_zero_values_round_trip_in_repository_dataframes():
    db = Database("sqlite:///:memory:")
    db.create_tables()
    obs_date = date(2026, 1, 2)

    with db.session() as session:
        source = SourceRepository(session).get_or_create("test", "test")
        series = MacroSeriesRepository(session).add(
            DimMacroSeries(fred_id="ZERO", name="Zero", category="test")
        )
        instrument = InstrumentRepository(session).add(
            DimInstrument(ticker="ZERO", asset_type="equity")
        )

        macro_repo = MacroRepository(session)
        macro_repo.upsert_batch(
            [{"series_id": series.series_id, "obs_date": obs_date, "value": 0.0}],
            source.source_id,
        )

        feature_repo = FeatureRepository(session)
        feature_repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": obs_date,
                    "feature_name": "zero_feature",
                    "source_id": source.source_id,
                    "value": 0.0,
                }
            ]
        )

        macro_df = macro_repo.get_as_dataframe([series.series_id])
        feature_df = feature_repo.get_features_for_date(obs_date)

        assert macro_df.loc[0, "value"] == 0.0
        assert feature_df.loc[0, "zero_feature"] == 0.0


@pytest.mark.asyncio
async def test_pipeline_create_run_failure_preserves_original_cause():
    class BrokenDatabase:
        @contextmanager
        def session(self):
            raise RuntimeError("create_run failed")
            yield

    orchestrator = PipelineOrchestrator.__new__(PipelineOrchestrator)
    orchestrator._initialized = True
    orchestrator._db = BrokenDatabase()

    with pytest.raises(PipelineError) as exc_info:
        await orchestrator.run(RunConfig(target_date=date(2026, 1, 2), providers=[]))

    assert exc_info.value.run_id is None
    assert isinstance(exc_info.value.cause, RuntimeError)
    assert "create_run failed" in str(exc_info.value.cause)
