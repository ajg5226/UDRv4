from contextlib import AbstractContextManager
from datetime import date

import pandas as pd
import pytest

import atlas.core.secrets as secrets_module
from atlas.core.config import get_settings
from atlas.core.exceptions import ConfigurationError, PipelineError
from atlas.dashboard.auth import (
    get_users,
    hash_password,
    validate_dashboard_auth_config,
    verify_password,
)
from atlas.pipeline.orchestrator import PipelineOrchestrator, RunConfig
from atlas.storage.database import Database, reset_database
from atlas.storage.repository import (
    FeatureRepository,
    InstrumentRepository,
    MacroRepository,
    MacroSeriesRepository,
    OHLCVRepository,
    SourceRepository,
)


@pytest.fixture(autouse=True)
def reset_cached_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATLAS_ENV", raising=False)
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.delenv("ATLAS_DASHBOARD__AUTH__ENABLED", raising=False)
    monkeypatch.delenv("ATLAS_DB_CONNECTION", raising=False)
    monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)

    get_settings.cache_clear()
    reset_database()

    monkeypatch.setattr(secrets_module, "_manager", None)
    yield
    get_settings.cache_clear()
    reset_database()


def test_production_dashboard_users_missing_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError):
        get_users()


def test_production_dashboard_users_malformed_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "{not-json")
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError):
        get_users()


def test_production_dashboard_uses_configured_users(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", f'{{"ops":"{hash_password("s3cret")}"}}')
    get_settings.cache_clear()

    assert verify_password("ops", "s3cret")
    assert not verify_password("admin", "atlas123")


def test_production_dashboard_auth_disable_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("ATLAS_DASHBOARD__AUTH__ENABLED", "false")
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError):
        validate_dashboard_auth_config()


def test_production_database_missing_connection_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_ENV", "production")
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError):
        Database()


def test_development_database_missing_connection_uses_sqlite() -> None:
    assert Database()._connection_string == "sqlite:///atlas_dev.db"


def test_ohlcv_sparse_update_preserves_existing_values_and_zero_readback() -> None:
    db = Database("sqlite:///:memory:")
    db.create_tables()

    trade_date = date(2026, 1, 5)
    with db.session() as session:
        source = SourceRepository(session).get_or_create("tiingo", "market")
        instruments = InstrumentRepository(session)
        instruments.upsert_from_dataframe(
            pd.DataFrame(
                [
                    {
                        "ticker": "SPY",
                        "name": "SPDR S&P 500 ETF",
                        "exchange": "NYSEARCA",
                        "asset_type": "etf",
                    }
                ]
            )
        )
        instrument = instruments.get_by_ticker("SPY", "NYSEARCA")
        assert instrument is not None

        repo = OHLCVRepository(session)
        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": trade_date,
                    "open": 0,
                    "high": 10,
                    "low": 9,
                    "close": 10,
                    "volume": 100,
                }
            ],
            source.source_id,
        )
        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": trade_date,
                    "open": float("nan"),
                    "high": None,
                    "low": 8,
                    "close": None,
                    "volume": None,
                }
            ],
            source.source_id,
        )

        row = repo.get_as_dataframe().iloc[0]

    assert row["open"] == 0
    assert row["high"] == 10
    assert row["low"] == 8
    assert row["close"] == 10
    assert row["volume"] == 100


def test_macro_and_feature_zero_values_round_trip() -> None:
    db = Database("sqlite:///:memory:")
    db.create_tables()

    trade_date = date(2026, 1, 5)
    with db.session() as session:
        source = SourceRepository(session).get_or_create("engine", "feature")
        instruments = InstrumentRepository(session)
        instruments.upsert_from_dataframe(
            pd.DataFrame(
                [
                    {
                        "ticker": "SPY",
                        "name": "SPDR S&P 500 ETF",
                        "exchange": "NYSEARCA",
                        "asset_type": "etf",
                    }
                ]
            )
        )
        instrument = instruments.get_by_ticker("SPY", "NYSEARCA")
        assert instrument is not None

        series = MacroSeriesRepository(session).get_or_create(
            "FEDFUNDS",
            "Federal Funds Rate",
            "rates",
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
                    "feature_name": "zero_signal",
                    "source_id": source.source_id,
                    "value": 0,
                }
            ]
        )

        macro_row = macro_repo.get_as_dataframe().iloc[0]
        feature_row = feature_repo.get_features_for_date(trade_date).iloc[0]

    assert macro_row["value"] == 0
    assert feature_row["zero_signal"] == 0


class FailingSession(AbstractContextManager[object]):
    def __enter__(self) -> object:
        raise RuntimeError("create run failed")

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> bool:
        return False


class FailingDatabase:
    def session(self) -> FailingSession:
        return FailingSession()


@pytest.mark.asyncio
async def test_pipeline_create_run_failure_preserves_original_error() -> None:
    orchestrator = PipelineOrchestrator.__new__(PipelineOrchestrator)
    orchestrator._initialized = True
    orchestrator._db = FailingDatabase()

    with pytest.raises(PipelineError) as exc_info:
        await orchestrator.run(RunConfig(target_date=date(2026, 1, 5)))

    assert exc_info.value.run_id is None
    assert isinstance(exc_info.value.cause, RuntimeError)
    assert str(exc_info.value.cause) == "create run failed"
