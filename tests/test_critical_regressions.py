"""Regression tests for high-impact production correctness failures."""

from __future__ import annotations

import hashlib
import importlib.util
from contextlib import nullcontext
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from atlas.core.config import get_settings
from atlas.core.exceptions import ConfigurationError, DatabaseError, PipelineError
import atlas.core.secrets as secrets_module
from atlas.dashboard.auth import get_users, verify_password
from atlas.pipeline import orchestrator as orchestrator_module
from atlas.pipeline.orchestrator import PipelineOrchestrator, RunConfig
from atlas.storage.database import Database, reset_database
from atlas.storage.models import DimInstrument, DimMacroSeries, DimSource
from atlas.storage.repository import (
    FeatureRepository,
    MacroRepository,
    OHLCVRepository,
)


@pytest.fixture(autouse=True)
def reset_global_state():
    """Keep cached settings, secrets, and database instances isolated."""
    get_settings.cache_clear()
    secrets_module._manager = None
    reset_database()
    yield
    get_settings.cache_clear()
    secrets_module._manager = None
    reset_database()


def _load_backfill_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "backfill_5year.py"
    spec = importlib.util.spec_from_file_location("backfill_5year", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _make_test_db() -> Database:
    db = Database(connection_string="sqlite:///:memory:")
    db.create_tables()
    return db


def _seed_dimensions(db: Database) -> tuple[int, int, int]:
    with db.session() as session:
        source = DimSource(name="test", provider_type="test")
        instrument = DimInstrument(ticker="ABC", exchange="NYSE", asset_type="equity")
        series = DimMacroSeries(fred_id="ZERO", name="Zero series", category="test")
        session.add_all([source, instrument, series])
        session.flush()
        return source.source_id, instrument.instrument_id, series.series_id


def test_dashboard_auth_fails_closed_without_production_users(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError):
        get_users()


def test_dashboard_auth_uses_configured_users(monkeypatch):
    password_hash = hashlib.sha256("safe-password".encode()).hexdigest()
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", f'{{"admin": "{password_hash}"}}')
    get_settings.cache_clear()

    assert get_users() == {"admin": password_hash}
    assert verify_password("admin", "safe-password")
    assert not verify_password("admin", "atlas123")


def test_database_fails_closed_without_production_connection(monkeypatch):
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DB_CONNECTION", raising=False)
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)
    get_settings.cache_clear()

    with pytest.raises(DatabaseError):
        Database()


def test_ohlcv_sparse_updates_do_not_erase_existing_values():
    db = _make_test_db()
    source_id, instrument_id, _ = _seed_dimensions(db)
    trade_date = date(2026, 1, 2)

    with db.session() as session:
        repo = OHLCVRepository(session)
        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument_id,
                    "trade_date": trade_date,
                    "open": 10,
                    "high": 12,
                    "low": 9,
                    "close": 11,
                    "volume": 100,
                    "dividend": 0,
                }
            ],
            source_id=source_id,
        )

    with db.session() as session:
        repo = OHLCVRepository(session)
        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument_id,
                    "trade_date": trade_date,
                    "open": None,
                    "high": float("nan"),
                    "low": 8,
                    "close": None,
                    "volume": 0,
                    "dividend": 1,
                }
            ],
            source_id=source_id,
        )

    with db.session() as session:
        row = OHLCVRepository(session).get_by_instrument_date(instrument_id, trade_date)
        assert float(row.open) == 10
        assert float(row.high) == 12
        assert float(row.low) == 8
        assert float(row.close) == 11
        assert row.volume == 0
        assert float(row.dividend) == 1


def test_repository_dataframe_exports_preserve_zero_values():
    db = _make_test_db()
    source_id, instrument_id, series_id = _seed_dimensions(db)
    trade_date = date(2026, 1, 2)

    with db.session() as session:
        OHLCVRepository(session).upsert_batch(
            [
                {
                    "instrument_id": instrument_id,
                    "trade_date": trade_date,
                    "open": 0,
                    "high": 0,
                    "low": 0,
                    "close": 0,
                    "volume": 0,
                    "adj_open": 0,
                    "adj_high": 0,
                    "adj_low": 0,
                    "adj_close": 0,
                    "adj_volume": 0,
                }
            ],
            source_id=source_id,
        )
        MacroRepository(session).upsert_batch(
            [{"series_id": series_id, "obs_date": trade_date, "value": 0}],
            source_id=source_id,
        )
        FeatureRepository(session).upsert_batch(
            [
                {
                    "instrument_id": instrument_id,
                    "trade_date": trade_date,
                    "feature_name": "zero_feature",
                    "value": 0,
                }
            ]
        )

    with db.session() as session:
        ohlcv_df = OHLCVRepository(session).get_as_dataframe()
        macro_df = MacroRepository(session).get_as_dataframe()
        feature_df = FeatureRepository(session).get_features_for_date(trade_date)

    assert ohlcv_df.loc[0, "open"] == 0
    assert ohlcv_df.loc[0, "adj_close"] == 0
    assert ohlcv_df.loc[0, "volume"] == 0
    assert macro_df.loc[0, "value"] == 0
    assert feature_df.loc[0, "zero_feature"] == 0


def test_feature_upsert_updates_lineage_metadata():
    db = _make_test_db()
    _, instrument_id, _ = _seed_dimensions(db)
    trade_date = date(2026, 1, 2)

    with db.session() as session:
        repo = FeatureRepository(session)
        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument_id,
                    "trade_date": trade_date,
                    "feature_name": "momentum",
                    "value": 1,
                    "feature_version": "1.0.0",
                    "params_hash": "old",
                    "transform_type": "raw",
                }
            ]
        )
        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument_id,
                    "trade_date": trade_date,
                    "feature_name": "momentum",
                    "value": 2,
                    "feature_version": "2.0.0",
                    "params_hash": "new",
                    "transform_type": "zscore",
                    "run_id": 7,
                }
            ]
        )
        row = repo.get_by_key(instrument_id, trade_date, "momentum")

    assert float(row.value) == 2
    assert row.feature_version == "2.0.0"
    assert row.params_hash == "new"
    assert row.transform_type == "zscore"
    assert row.run_id == 7


def test_backfill_macro_records_use_fred_obs_date():
    backfill = _load_backfill_module()

    record = backfill._build_macro_record(
        {"obs_date": date(2026, 1, 2), "value": 4.5},
        series_id=12,
        source_id=34,
    )

    assert record == {
        "series_id": 12,
        "source_id": 34,
        "obs_date": date(2026, 1, 2),
        "value": 4.5,
    }


@pytest.mark.asyncio
async def test_pipeline_preserves_create_run_failure(monkeypatch):
    class FailingRunRepository:
        def __init__(self, session):
            pass

        def create_run(self, **kwargs):
            raise RuntimeError("database unavailable")

    class FakeDatabase:
        def session(self):
            return nullcontext(object())

    orchestrator = PipelineOrchestrator.__new__(PipelineOrchestrator)
    orchestrator._initialized = True
    orchestrator._db = FakeDatabase()
    orchestrator._settings = SimpleNamespace(features=SimpleNamespace(enabled=False))

    monkeypatch.setattr(orchestrator_module, "PipelineRunRepository", FailingRunRepository)

    with pytest.raises(PipelineError) as exc_info:
        await orchestrator.run(RunConfig(skip_features=True))

    assert exc_info.value.run_id is None
    assert isinstance(exc_info.value.cause, RuntimeError)
    assert str(exc_info.value.cause) == "database unavailable"
