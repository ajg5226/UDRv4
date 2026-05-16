"""Regression tests for repository persistence and readback semantics."""

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from atlas.storage.models import Base, DimInstrument, DimMacroSeries, DimSource
from atlas.storage.repository import FeatureRepository, MacroRepository, OHLCVRepository


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def source(session):
    source = DimSource(name="tiingo", provider_type="market_data")
    session.add(source)
    session.flush()
    return source


@pytest.fixture
def instrument(session):
    instrument = DimInstrument(ticker="ABC", asset_type="equity")
    session.add(instrument)
    session.flush()
    return instrument


@pytest.fixture
def macro_series(session):
    series = DimMacroSeries(fred_id="ZERO", name="Zero Series", category="test")
    session.add(series)
    session.flush()
    return series


def test_ohlcv_sparse_update_preserves_existing_values(session, source, instrument) -> None:
    repo = OHLCVRepository(session)
    trade_date = date(2024, 1, 2)

    repo.upsert_batch(
        [
            {
                "instrument_id": instrument.instrument_id,
                "trade_date": trade_date,
                "open": Decimal("10.00"),
                "high": Decimal("11.00"),
                "low": Decimal("9.00"),
                "close": Decimal("10.50"),
                "volume": 100,
                "adj_close": Decimal("10.25"),
                "dividend": Decimal("0.00"),
                "split_factor": Decimal("1.00"),
            }
        ],
        source.source_id,
    )

    inserted, updated = repo.upsert_batch(
        [
            {
                "instrument_id": instrument.instrument_id,
                "trade_date": trade_date,
                "open": Decimal("10.75"),
                "high": None,
                "low": float("nan"),
                "close": Decimal("10.80"),
                "volume": None,
                "adj_close": pd.NA,
                "dividend": None,
                "split_factor": None,
            }
        ],
        source.source_id,
    )

    row = repo.get_by_instrument_date(instrument.instrument_id, trade_date)

    assert (inserted, updated) == (0, 1)
    assert row.open == Decimal("10.750000")
    assert row.high == Decimal("11.000000")
    assert row.low == Decimal("9.000000")
    assert row.close == Decimal("10.800000")
    assert row.volume == 100
    assert row.adj_close == Decimal("10.250000")
    assert row.dividend == Decimal("0.000000")
    assert row.split_factor == Decimal("1.000000")


def test_repository_dataframes_preserve_zero_values(
    session, source, instrument, macro_series
) -> None:
    ohlcv_repo = OHLCVRepository(session)
    macro_repo = MacroRepository(session)
    feature_repo = FeatureRepository(session)
    trade_date = date(2024, 1, 2)

    ohlcv_repo.upsert_batch(
        [
            {
                "instrument_id": instrument.instrument_id,
                "trade_date": trade_date,
                "open": Decimal("0"),
                "high": Decimal("0"),
                "low": Decimal("0"),
                "close": Decimal("0"),
                "volume": 0,
                "adj_open": Decimal("0"),
                "adj_high": Decimal("0"),
                "adj_low": Decimal("0"),
                "adj_close": Decimal("0"),
                "adj_volume": 0,
            }
        ],
        source.source_id,
    )
    macro_repo.upsert_batch(
        [{"series_id": macro_series.series_id, "obs_date": trade_date, "value": Decimal("0")}],
        source.source_id,
    )
    feature_repo.upsert_batch(
        [
            {
                "instrument_id": instrument.instrument_id,
                "trade_date": trade_date,
                "feature_name": "zero_feature",
                "value": Decimal("0"),
            }
        ],
    )

    ohlcv_df = ohlcv_repo.get_as_dataframe([instrument.instrument_id], trade_date, trade_date)
    macro_df = macro_repo.get_as_dataframe(
        [macro_series.series_id],
        start_date=trade_date,
        end_date=trade_date,
    )
    feature_df = feature_repo.get_features_for_date(trade_date)

    assert ohlcv_df.loc[0, "open"] == 0.0
    assert ohlcv_df.loc[0, "close"] == 0.0
    assert ohlcv_df.loc[0, "adj_close"] == 0.0
    assert macro_df.loc[0, "value"] == 0.0
    assert feature_df.loc[0, "zero_feature"] == 0.0
