from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from atlas.storage.models import (
    Base,
    DimInstrument,
    DimMacroSeries,
    DimSource,
    FactFeature,
    FactMacro,
    FactOHLCV,
)
from atlas.storage.repository import FeatureRepository, MacroRepository, OHLCVRepository


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with session_factory() as db_session:
        yield db_session

    Base.metadata.drop_all(engine)
    engine.dispose()


def _source(session) -> DimSource:
    source = DimSource(name="tiingo", provider_type="market")
    session.add(source)
    session.flush()
    return source


def _instrument(session) -> DimInstrument:
    instrument = DimInstrument(ticker="ZERO", asset_type="equity")
    session.add(instrument)
    session.flush()
    return instrument


def test_ohlcv_upsert_does_not_overwrite_existing_values_with_missing_data(session):
    source = _source(session)
    instrument = _instrument(session)
    trade_date = date(2024, 1, 2)
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
                "volume": 100,
                "adj_close": 10.25,
                "dividend": 0.1,
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
                "high": 12.0,
                "low": pd.NA,
                "close": None,
                "volume": 200,
                "adj_close": None,
                "dividend": 0.0,
            }
        ],
        source.source_id,
    )

    updated = repo.get_by_instrument_date(instrument.instrument_id, trade_date)

    assert updated.open == Decimal("10.000000")
    assert updated.high == Decimal("12.000000")
    assert updated.low == Decimal("9.500000")
    assert updated.close == Decimal("10.500000")
    assert updated.volume == 200
    assert updated.adj_close == Decimal("10.250000")
    assert updated.dividend == Decimal("0.000000")


def test_repository_dataframe_readbacks_preserve_numeric_zero_values(session):
    source = _source(session)
    instrument = _instrument(session)
    series = DimMacroSeries(fred_id="ZERO_RATE", name="Zero Rate", category="rates")
    session.add(series)
    session.flush()

    trade_date = date(2024, 1, 2)
    session.add_all(
        [
            FactOHLCV(
                instrument_id=instrument.instrument_id,
                trade_date=trade_date,
                source_id=source.source_id,
                open=Decimal("0"),
                high=Decimal("0"),
                low=Decimal("0"),
                close=Decimal("0"),
                volume=0,
                adj_open=Decimal("0"),
                adj_high=Decimal("0"),
                adj_low=Decimal("0"),
                adj_close=Decimal("0"),
                adj_volume=0,
            ),
            FactMacro(
                series_id=series.series_id,
                obs_date=trade_date,
                source_id=source.source_id,
                value=Decimal("0"),
            ),
            FactFeature(
                instrument_id=instrument.instrument_id,
                trade_date=trade_date,
                feature_name="zero_feature",
                value=Decimal("0"),
            ),
        ]
    )
    session.flush()

    ohlcv = OHLCVRepository(session).get_as_dataframe()
    macro = MacroRepository(session).get_as_dataframe()
    features = FeatureRepository(session).get_features_for_date(trade_date)

    assert ohlcv.loc[0, "open"] == 0.0
    assert ohlcv.loc[0, "adj_close"] == 0.0
    assert macro.loc[0, "value"] == 0.0
    assert features.loc[0, "zero_feature"] == 0.0


def test_feature_upsert_refreshes_lineage_metadata(session):
    instrument = _instrument(session)
    repo = FeatureRepository(session)
    trade_date = date(2024, 1, 2)
    first_calc = datetime(2024, 1, 2, 6, 0, 0)
    second_calc = datetime(2024, 1, 3, 6, 0, 0)

    repo.upsert_batch(
        [
            {
                "instrument_id": instrument.instrument_id,
                "trade_date": trade_date,
                "feature_name": "momentum",
                "value": 1.0,
                "feature_version": "1.0.0",
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
                "value": 2.0,
                "feature_version": "2.0.0",
                "params_hash": "new",
                "transform_type": "zscore",
                "calc_timestamp": second_calc,
            }
        ],
        run_id=2,
    )

    updated = repo.get_by_key(instrument.instrument_id, trade_date, "momentum")

    assert updated.value == Decimal("2.000000")
    assert updated.feature_version == "2.0.0"
    assert updated.params_hash == "new"
    assert updated.transform_type == "zscore"
    assert updated.calc_timestamp == second_calc
    assert updated.run_id == 2
