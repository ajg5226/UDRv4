"""Shared test fixtures for ATLAS test suite."""

import os
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from atlas.storage.models import (
    Base,
    DimInstrument,
    DimMacroSeries,
    DimSource,
    FactMacro,
    FactOHLCV,
    PipelineRun,
)


@pytest.fixture(autouse=True)
def _set_test_env(monkeypatch):
    """Set environment variables for all tests."""
    monkeypatch.setenv("ATLAS_ENV", "development")
    monkeypatch.setenv("ATLAS_DB_CONNECTION", "sqlite:///:memory:")
    monkeypatch.setenv("TIINGO_API_KEY", "test_tiingo_key")
    monkeypatch.setenv("FRED_API_KEY", "test_fred_key")


@pytest.fixture(autouse=True)
def _clear_caches():
    """Clear all LRU caches between tests."""
    from atlas.core.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def db_engine():
    """Create an in-memory SQLite engine with all tables."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """Create a database session for testing."""
    factory = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    session = factory()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def sample_source(db_session: Session) -> DimSource:
    """Create a sample data source."""
    source = DimSource(name="test_provider", provider_type="market_data", base_url="https://test.com")
    db_session.add(source)
    db_session.flush()
    return source


@pytest.fixture
def sample_instruments(db_session: Session) -> list[DimInstrument]:
    """Create sample instruments."""
    instruments = [
        DimInstrument(ticker="AAPL", asset_type="equity", name="Apple Inc.", tiingo_ticker="AAPL"),
        DimInstrument(ticker="MSFT", asset_type="equity", name="Microsoft Corp.", tiingo_ticker="MSFT"),
        DimInstrument(ticker="SPY", asset_type="etf", name="SPDR S&P 500 ETF", tiingo_ticker="SPY"),
    ]
    db_session.add_all(instruments)
    db_session.flush()
    return instruments


@pytest.fixture
def sample_macro_series(db_session: Session) -> list[DimMacroSeries]:
    """Create sample macro series."""
    series = [
        DimMacroSeries(fred_id="DFF", name="Effective Federal Funds Rate", category="liquidity"),
        DimMacroSeries(fred_id="DGS10", name="10-Year Treasury", category="liquidity"),
        DimMacroSeries(fred_id="VIXCLS", name="VIX Index", category="risk_appetite"),
    ]
    db_session.add_all(series)
    db_session.flush()
    return series


@pytest.fixture
def sample_ohlcv_data(
    db_session: Session,
    sample_source: DimSource,
    sample_instruments: list[DimInstrument],
) -> list[FactOHLCV]:
    """Create 30 days of OHLCV data for each instrument."""
    records = []
    base_date = date(2026, 2, 1)
    base_prices = {"AAPL": 250.0, "MSFT": 380.0, "SPY": 680.0}

    rng = np.random.default_rng(42)
    for inst in sample_instruments:
        price = base_prices.get(inst.ticker, 100.0)
        for i in range(30):
            d = base_date + timedelta(days=i)
            if d.weekday() >= 5:
                continue
            daily_return = rng.normal(0.001, 0.015)
            price *= 1 + daily_return
            record = FactOHLCV(
                instrument_id=inst.instrument_id,
                trade_date=d,
                source_id=sample_source.source_id,
                open=Decimal(str(round(price * 0.998, 2))),
                high=Decimal(str(round(price * 1.01, 2))),
                low=Decimal(str(round(price * 0.99, 2))),
                close=Decimal(str(round(price, 2))),
                volume=1_000_000 + rng.integers(-200_000, 200_000),
                adj_open=Decimal(str(round(price * 0.998, 2))),
                adj_high=Decimal(str(round(price * 1.01, 2))),
                adj_low=Decimal(str(round(price * 0.99, 2))),
                adj_close=Decimal(str(round(price, 2))),
                adj_volume=1_000_000 + rng.integers(-200_000, 200_000),
            )
            records.append(record)
    db_session.add_all(records)
    db_session.flush()
    return records


@pytest.fixture
def ohlcv_dataframe(sample_ohlcv_data: list[FactOHLCV]) -> pd.DataFrame:
    """Convert sample OHLCV data into a DataFrame matching repo output format."""
    rows = []
    for r in sample_ohlcv_data:
        rows.append({
            "instrument_id": r.instrument_id,
            "trade_date": r.trade_date,
            "open": float(r.open),
            "high": float(r.high),
            "low": float(r.low),
            "close": float(r.close),
            "volume": r.volume,
            "adj_close": float(r.adj_close),
            "adj_open": float(r.adj_open),
            "adj_high": float(r.adj_high),
            "adj_low": float(r.adj_low),
            "adj_volume": r.adj_volume,
        })
    return pd.DataFrame(rows)
