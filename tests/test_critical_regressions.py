import importlib.util
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from atlas.core.config import Settings
from atlas.core.exceptions import ConfigurationError, PipelineError
from atlas.dashboard import auth
from atlas.pipeline.orchestrator import PipelineOrchestrator, RunConfig
from atlas.storage import database
from atlas.storage.models import Base, DimInstrument, DimSource
from atlas.storage.repository import OHLCVRepository

BACKFILL_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "backfill_5year.py"
BACKFILL_SPEC = importlib.util.spec_from_file_location("backfill_5year", BACKFILL_SCRIPT)
assert BACKFILL_SPEC is not None
backfill_5year = importlib.util.module_from_spec(BACKFILL_SPEC)
assert BACKFILL_SPEC.loader is not None
BACKFILL_SPEC.loader.exec_module(backfill_5year)


def test_production_dashboard_auth_requires_configured_users(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_secret", lambda _name: None)
    settings = Settings(ATLAS_ENV="production")

    with pytest.raises(ConfigurationError):
        auth.get_users(settings)


def test_production_dashboard_auth_rejects_malformed_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_DASHBOARD_USERS", "{not-json")
    monkeypatch.setattr(auth, "get_secret", lambda _name: None)
    settings = Settings(ATLAS_ENV="production")

    with pytest.raises(ConfigurationError):
        auth.get_users(settings)


def test_dashboard_auth_defaults_are_development_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATLAS_DASHBOARD_USERS", raising=False)
    monkeypatch.setattr(auth, "get_secret", lambda _name: None)
    settings = Settings(ATLAS_ENV="development")

    users = auth.get_users(settings)

    assert auth.hash_password("atlas123") == users["admin"]
    assert auth.hash_password("atlas123") == users["analyst"]


def test_production_dashboard_auth_cannot_be_disabled() -> None:
    settings = Settings(
        ATLAS_ENV="production",
        dashboard={"auth": {"enabled": False}},
    )

    with pytest.raises(ConfigurationError):
        auth.ensure_dashboard_auth_configured(settings)


def test_production_database_connection_does_not_fallback_to_sqlite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ATLAS_DB_CONNECTION", raising=False)
    monkeypatch.setattr(database, "get_secret", lambda _name: None)
    monkeypatch.setattr(database, "get_settings", lambda: Settings(ATLAS_ENV="production"))

    with pytest.raises(ConfigurationError):
        database.Database()


def test_ohlcv_upsert_skips_missing_update_values_but_preserves_zeroes() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        source = DimSource(name="tiingo", provider_type="market")
        instrument = DimInstrument(ticker="AAPL", asset_type="equity")
        session.add_all([source, instrument])
        session.flush()

        repo = OHLCVRepository(session)
        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": date(2026, 1, 2),
                    "open": Decimal("100"),
                    "high": Decimal("110"),
                    "low": Decimal("90"),
                    "close": Decimal("105"),
                    "volume": 1000,
                    "adj_close": Decimal("105"),
                }
            ],
            source.source_id,
        )
        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": date(2026, 1, 2),
                    "open": None,
                    "high": pd.NA,
                    "low": float("nan"),
                    "close": Decimal("0"),
                    "volume": 0,
                    "adj_close": None,
                }
            ],
            source.source_id,
        )

        row = repo.get_by_instrument_date(instrument.instrument_id, date(2026, 1, 2))

    assert row is not None
    assert row.open == Decimal("100.000000")
    assert row.high == Decimal("110.000000")
    assert row.low == Decimal("90.000000")
    assert row.close == Decimal("0.000000")
    assert row.volume == 0
    assert row.adj_close == Decimal("105.000000")


def test_backfill_macro_records_use_fred_obs_date_column() -> None:
    df = pd.DataFrame(
        [
            {"fred_id": "GDP", "obs_date": date(2026, 1, 1), "value": Decimal("123.45")},
            {"fred_id": "GDP", "obs_date": date(2026, 2, 1), "value": None},
        ]
    )

    records = backfill_5year.build_macro_records(df, {"GDP": 7}, fred_source_id=3)

    assert records == [
        {
            "series_id": 7,
            "source_id": 3,
            "obs_date": date(2026, 1, 1),
            "value": Decimal("123.45"),
        }
    ]


@pytest.mark.asyncio
async def test_pipeline_default_instruments_come_from_active_database_rows() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        session.add_all(
            [
                DimInstrument(ticker="AAPL", asset_type="equity", is_active=True),
                DimInstrument(ticker="MSFT", asset_type="equity", is_active=True),
                DimInstrument(ticker="OLD", asset_type="equity", is_active=False),
            ]
        )
        session.commit()

    class TestDatabase:
        @contextmanager
        def session(self):
            session = session_factory()
            try:
                yield session
            finally:
                session.close()

    orchestrator = PipelineOrchestrator.__new__(PipelineOrchestrator)
    orchestrator._db = TestDatabase()

    tickers = await orchestrator._get_instruments(RunConfig(), required=True)

    assert tickers == ["AAPL", "MSFT"]


@pytest.mark.asyncio
async def test_pipeline_early_run_creation_failure_preserves_original_cause() -> None:
    class BrokenDatabase:
        def session(self):
            raise RuntimeError("database unavailable")

    orchestrator = PipelineOrchestrator.__new__(PipelineOrchestrator)
    orchestrator._initialized = True
    orchestrator._db = BrokenDatabase()

    with pytest.raises(PipelineError) as exc_info:
        await orchestrator.run(RunConfig())

    assert exc_info.value.run_id is None
    assert isinstance(exc_info.value.cause, RuntimeError)
    assert "database unavailable" in str(exc_info.value.cause)
