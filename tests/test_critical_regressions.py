"""Regression tests for high-severity correctness and fail-closed behavior."""

from __future__ import annotations

import json
import importlib.util
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from atlas.core.config import get_settings
from atlas.core.exceptions import ConfigurationError, DatabaseError, PipelineError
from atlas.dashboard.auth import get_users, hash_password, verify_password
from atlas.pipeline.orchestrator import PipelineOrchestrator, RunConfig
from atlas.storage.database import Database, reset_database
from atlas.storage.models import DimInstrument
from atlas.storage.repository import (
    FeatureRepository,
    InstrumentRepository,
    OHLCVRepository,
    SourceRepository,
)


_BACKFILL_PATH = Path(__file__).resolve().parents[1] / "scripts" / "backfill_5year.py"
_BACKFILL_SPEC = importlib.util.spec_from_file_location("backfill_5year", _BACKFILL_PATH)
_backfill_module = importlib.util.module_from_spec(_BACKFILL_SPEC)
assert _BACKFILL_SPEC.loader is not None
_BACKFILL_SPEC.loader.exec_module(_backfill_module)
_build_macro_record = _backfill_module._build_macro_record


@pytest.fixture(autouse=True)
def clear_cached_state():
    get_settings.cache_clear()
    reset_database()
    yield
    get_settings.cache_clear()
    reset_database()


def test_dashboard_users_fail_closed_without_production_credentials(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr("atlas.core.secrets.get_secret", lambda name, default=None: None)
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError, match="Dashboard user credentials are required"):
        get_users()


def test_dashboard_users_accept_configured_production_credentials(monkeypatch):
    password_hash = hash_password("correct horse battery staple")
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", json.dumps({"alice": password_hash}))
    get_settings.cache_clear()

    assert get_users() == {"alice": password_hash}
    assert verify_password("alice", "correct horse battery staple")
    assert not verify_password("alice", "wrong")


def test_database_fails_closed_without_production_connection(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DB_CONNECTION", raising=False)
    monkeypatch.setattr("atlas.core.secrets.get_secret", lambda name, default=None: None)
    get_settings.cache_clear()

    with pytest.raises(DatabaseError, match="Database connection string is required"):
        Database()


def test_ohlcv_upsert_preserves_existing_values_when_update_has_missing_fields():
    db = Database("sqlite:///:memory:")
    db.create_tables()
    trade_date = date(2026, 1, 2)

    with db.session() as session:
        source = SourceRepository(session).get_or_create("tiingo", "market_data")
        instrument = InstrumentRepository(session).add(
            DimInstrument(ticker="ZERO", asset_type="equity")
        )
        repo = OHLCVRepository(session)

        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": trade_date,
                    "open": 10.0,
                    "high": 11.0,
                    "low": 9.5,
                    "close": 10.5,
                    "volume": 0,
                    "adj_open": 10.0,
                    "adj_high": 11.0,
                    "adj_low": 9.5,
                    "adj_close": 10.5,
                    "adj_volume": 0,
                }
            ],
            source.source_id,
        )

        inserted, updated = repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": trade_date,
                    "open": None,
                    "high": float("nan"),
                    "low": None,
                    "close": 0.0,
                    "volume": None,
                    "adj_open": None,
                    "adj_high": None,
                    "adj_low": None,
                    "adj_close": None,
                    "adj_volume": None,
                }
            ],
            source.source_id,
        )

        assert (inserted, updated) == (0, 1)
        saved = repo.get_by_instrument_date(instrument.instrument_id, trade_date)
        assert float(saved.open) == 10.0
        assert float(saved.high) == 11.0
        assert float(saved.close) == 0.0
        assert saved.volume == 0

        df = repo.get_as_dataframe([instrument.instrument_id], trade_date, trade_date)
        assert df.loc[0, "close"] == 0.0
        assert df.loc[0, "volume"] == 0


def test_feature_upsert_refreshes_lineage_metadata_and_preserves_zero_value():
    db = Database("sqlite:///:memory:")
    db.create_tables()
    trade_date = date(2026, 1, 2)

    with db.session() as session:
        instrument = InstrumentRepository(session).add(
            DimInstrument(ticker="META", asset_type="equity")
        )
        repo = FeatureRepository(session)

        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": trade_date,
                    "feature_name": "momentum",
                    "value": 1.5,
                    "feature_version": "v1",
                    "params_hash": "old",
                    "transform_type": "raw",
                    "calc_timestamp": datetime(2026, 1, 2, 12, 0, 0),
                }
            ]
        )
        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": trade_date,
                    "feature_name": "momentum",
                    "value": 0.0,
                    "feature_version": "v2",
                    "params_hash": "new",
                    "transform_type": "zscore",
                    "calc_timestamp": datetime(2026, 1, 3, 12, 0, 0),
                }
            ]
        )

        saved = repo.get_by_key(instrument.instrument_id, trade_date, "momentum")
        assert float(saved.value) == 0.0
        assert saved.feature_version == "v2"
        assert saved.params_hash == "new"
        assert saved.transform_type == "zscore"

        df = repo.get_features_for_date(trade_date)
        assert df.loc[0, "momentum"] == 0.0


@pytest.mark.asyncio
async def test_pipeline_create_run_failure_preserves_original_error():
    class FailingDatabase:
        def session(self):
            raise RuntimeError("primary database unavailable")

    orchestrator = PipelineOrchestrator.__new__(PipelineOrchestrator)
    orchestrator._initialized = True
    orchestrator._db = FailingDatabase()
    orchestrator._settings = SimpleNamespace(features=SimpleNamespace(enabled=False))

    with pytest.raises(PipelineError) as exc_info:
        await orchestrator.run(RunConfig(skip_features=True))

    assert exc_info.value.run_id is None
    assert isinstance(exc_info.value.cause, RuntimeError)
    assert "primary database unavailable" in str(exc_info.value.cause)


def test_macro_backfill_uses_fred_obs_date_column():
    record = _build_macro_record(
        {"fred_id": "GDP", "obs_date": date(2026, 1, 1), "value": 0.0},
        db_series_id=7,
        fred_source_id=3,
    )

    assert record == {
        "series_id": 7,
        "source_id": 3,
        "obs_date": date(2026, 1, 1),
        "value": 0.0,
    }


def test_macro_backfill_keeps_legacy_date_fallback():
    record = _build_macro_record(
        {"fred_id": "GDP", "date": "2026-01-01", "value": 1.25},
        db_series_id=7,
        fred_source_id=3,
    )

    assert record["obs_date"] == date(2026, 1, 1)
