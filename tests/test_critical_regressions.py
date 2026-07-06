import asyncio
import hashlib
import json
from contextlib import AbstractContextManager
from datetime import date
from decimal import Decimal
from types import TracebackType

import pandas as pd
import pytest

import atlas.core.secrets as secrets_module
from atlas.core.config import reload_settings
from atlas.core.exceptions import ConfigurationError, PipelineError
from atlas.dashboard.auth import get_users, verify_password
from atlas.pipeline.orchestrator import PipelineOrchestrator, RunConfig, RunType
from atlas.storage.database import Database, reset_database
from atlas.storage.models import DimInstrument, DimMacroSeries, DimSource, FactFeature
from atlas.storage.repository import FeatureRepository, MacroRepository, OHLCVRepository
from scripts.backfill_5year import coerce_provider_date


@pytest.fixture(autouse=True)
def reset_global_state():
    reset_database()
    reload_settings()
    secrets_module._manager = None
    yield
    reset_database()
    reload_settings()
    secrets_module._manager = None


def _reload_after_env_change() -> None:
    reload_settings()
    secrets_module._manager = None


def _sqlite_database() -> Database:
    db = Database("sqlite:///:memory:")
    db.create_tables()
    return db


def _seed_source_and_instrument(db: Database) -> tuple[int, int]:
    with db.session() as session:
        source = DimSource(name="tiingo", provider_type="market_data")
        instrument = DimInstrument(ticker="ZERO", asset_type="equity")
        session.add_all([source, instrument])
        session.flush()
        return source.source_id, instrument.instrument_id


def test_production_dashboard_requires_configured_users(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)
    _reload_after_env_change()

    with pytest.raises(ConfigurationError, match="Dashboard users secret is required"):
        get_users()


def test_production_dashboard_uses_configured_secret_not_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    password_hash = hashlib.sha256("s3cret".encode()).hexdigest()
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", json.dumps({"ops": password_hash}))
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)
    _reload_after_env_change()

    assert get_users() == {"ops": password_hash}
    assert verify_password("ops", "s3cret")
    assert not verify_password("admin", "atlas123")


def test_production_database_requires_configured_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.delenv("ATLAS_DB_CONNECTION", raising=False)
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)
    _reload_after_env_change()

    with pytest.raises(ConfigurationError, match="Database connection string is required"):
        Database()


def test_ohlcv_sparse_update_preserves_existing_values_and_reads_zeroes() -> None:
    db = _sqlite_database()
    source_id, instrument_id = _seed_source_and_instrument(db)

    with db.session() as session:
        repo = OHLCVRepository(session)
        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument_id,
                    "trade_date": date(2026, 1, 2),
                    "open": Decimal("10"),
                    "high": Decimal("11"),
                    "low": Decimal("9"),
                    "close": Decimal("10.5"),
                    "volume": 100,
                    "adj_close": Decimal("10.5"),
                    "dividend": Decimal("0"),
                    "split_factor": Decimal("1"),
                }
            ],
            source_id,
        )
        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument_id,
                    "trade_date": date(2026, 1, 2),
                    "open": pd.NA,
                    "high": None,
                    "low": float("nan"),
                    "close": None,
                    "volume": 0,
                    "adj_close": None,
                }
            ],
            source_id,
        )
        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument_id,
                    "trade_date": date(2026, 1, 3),
                    "open": Decimal("0"),
                    "high": Decimal("0"),
                    "low": Decimal("0"),
                    "close": Decimal("0"),
                    "volume": 0,
                    "adj_close": Decimal("0"),
                }
            ],
            source_id,
        )

        df = repo.get_as_dataframe(instrument_ids=[instrument_id])

    first_row = df[df["trade_date"] == date(2026, 1, 2)].iloc[0]
    assert first_row["open"] == 10.0
    assert first_row["high"] == 11.0
    assert first_row["low"] == 9.0
    assert first_row["close"] == 10.5
    assert first_row["adj_close"] == 10.5
    assert first_row["volume"] == 0

    zero_row = df[df["trade_date"] == date(2026, 1, 3)].iloc[0]
    assert zero_row["open"] == 0.0
    assert zero_row["close"] == 0.0
    assert zero_row["adj_close"] == 0.0


def test_macro_and_feature_zero_readback_and_feature_lineage_refresh() -> None:
    db = _sqlite_database()
    source_id, instrument_id = _seed_source_and_instrument(db)

    with db.session() as session:
        series = DimMacroSeries(fred_id="ZERO", name="Zero Series", category="growth")
        session.add(series)
        session.flush()

        macro_repo = MacroRepository(session)
        macro_repo.upsert_batch(
            [
                {
                    "series_id": series.series_id,
                    "obs_date": date(2026, 1, 2),
                    "value": Decimal("0"),
                }
            ],
            source_id,
        )
        macro_df = macro_repo.get_as_dataframe(series_ids=[series.series_id])

        feature_repo = FeatureRepository(session)
        feature_repo.upsert_batch(
            [
                {
                    "instrument_id": instrument_id,
                    "trade_date": date(2026, 1, 2),
                    "feature_name": "signal",
                    "value": Decimal("1"),
                    "feature_version": "1.0.0",
                    "params_hash": "old",
                    "transform_type": "raw",
                }
            ],
        )
        feature_repo.upsert_batch(
            [
                {
                    "instrument_id": instrument_id,
                    "trade_date": date(2026, 1, 2),
                    "feature_name": "signal",
                    "value": Decimal("0"),
                    "feature_version": "2.0.0",
                    "params_hash": "new",
                    "transform_type": "zscore",
                }
            ],
            run_id=42,
        )
        feature_df = feature_repo.get_features_for_date(date(2026, 1, 2))
        feature = session.get(
            FactFeature,
            {
                "instrument_id": instrument_id,
                "trade_date": date(2026, 1, 2),
                "feature_name": "signal",
            },
        )

    assert macro_df.iloc[0]["value"] == 0.0
    assert feature_df.iloc[0]["signal"] == 0.0
    assert feature is not None
    assert feature.feature_version == "2.0.0"
    assert feature.params_hash == "new"
    assert feature.transform_type == "zscore"
    assert feature.run_id == 42


def test_pipeline_create_run_failure_preserves_original_cause() -> None:
    class FailingSession(AbstractContextManager[object]):
        def __enter__(self) -> object:
            raise RuntimeError("create-run failed")

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_value: BaseException | None,
            traceback: TracebackType | None,
        ) -> bool | None:
            return None

    class FailingDatabase:
        def session(self) -> FailingSession:
            return FailingSession()

    orchestrator = PipelineOrchestrator.__new__(PipelineOrchestrator)
    orchestrator._initialized = True
    orchestrator._db = FailingDatabase()

    async def run() -> None:
        with pytest.raises(PipelineError) as exc_info:
            await orchestrator.run(RunConfig(run_type=RunType.MANUAL, target_date=date(2026, 1, 2)))

        assert exc_info.value.run_id is None
        assert isinstance(exc_info.value.cause, RuntimeError)
        assert str(exc_info.value.cause) == "create-run failed"

    asyncio.run(run())


def test_backfill_script_accepts_fred_obs_date_column() -> None:
    assert coerce_provider_date(pd.Timestamp("2026-01-02")) == date(2026, 1, 2)
    assert coerce_provider_date("2026-01-02T00:00:00") == date(2026, 1, 2)
