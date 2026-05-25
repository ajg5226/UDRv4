from datetime import date, datetime
from decimal import Decimal

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from atlas.storage.models import Base, DimInstrument, DimMacroSeries, DimSource
from atlas.storage.repository import FeatureRepository, MacroRepository, OHLCVRepository


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    return session_factory()


def seed_dimensions(session):
    source = DimSource(name="tiingo", provider_type="ohlcv")
    instrument = DimInstrument(ticker="ABC", asset_type="equity")
    macro_series = DimMacroSeries(fred_id="TEST", name="Test Series", category="growth")
    session.add_all([source, instrument, macro_series])
    session.flush()
    return source, instrument, macro_series


def test_ohlcv_sparse_update_preserves_existing_prices():
    session = make_session()
    source, instrument, _ = seed_dimensions(session)
    repo = OHLCVRepository(session)
    trade_date = date(2026, 5, 22)

    inserted, updated = repo.upsert_batch(
        [
            {
                "instrument_id": instrument.instrument_id,
                "trade_date": trade_date,
                "open": Decimal("10.00"),
                "high": Decimal("12.00"),
                "low": Decimal("9.50"),
                "close": Decimal("11.00"),
                "volume": 1000,
                "adj_close": Decimal("11.00"),
            }
        ],
        source.source_id,
    )

    assert (inserted, updated) == (1, 0)

    inserted, updated = repo.upsert_batch(
        [
            {
                "instrument_id": instrument.instrument_id,
                "trade_date": trade_date,
                "open": None,
                "high": pd.NA,
                "low": Decimal("9.75"),
                "close": None,
                "volume": 0,
                "adj_close": None,
            }
        ],
        source.source_id,
    )

    row = repo.get_by_instrument_date(instrument.instrument_id, trade_date)

    assert (inserted, updated) == (0, 1)
    assert row.open == Decimal("10.000000")
    assert row.high == Decimal("12.000000")
    assert row.low == Decimal("9.750000")
    assert row.close == Decimal("11.000000")
    assert row.volume == 0
    assert row.adj_close == Decimal("11.000000")


def test_repository_dataframe_readback_preserves_numeric_zeroes():
    session = make_session()
    source, instrument, macro_series = seed_dimensions(session)
    ohlcv_repo = OHLCVRepository(session)
    macro_repo = MacroRepository(session)
    feature_repo = FeatureRepository(session)
    trade_date = date(2026, 5, 22)

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
                "adj_close": Decimal("0"),
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
                "feature_version": "1.0.0",
            }
        ],
    )

    ohlcv_df = ohlcv_repo.get_as_dataframe()
    macro_df = macro_repo.get_as_dataframe()
    feature_df = feature_repo.get_features_for_date(trade_date)

    assert ohlcv_df.loc[0, "open"] == 0.0
    assert ohlcv_df.loc[0, "close"] == 0.0
    assert macro_df.loc[0, "value"] == 0.0
    assert feature_df.loc[0, "zero_feature"] == 0.0


def test_feature_upsert_refreshes_lineage_metadata():
    session = make_session()
    source, instrument, _ = seed_dimensions(session)
    repo = FeatureRepository(session)
    trade_date = date(2026, 5, 22)
    first_calc = datetime(2026, 5, 22, 10, 0, 0)
    second_calc = datetime(2026, 5, 22, 11, 0, 0)

    repo.upsert_batch(
        [
            {
                "instrument_id": instrument.instrument_id,
                "trade_date": trade_date,
                "feature_name": "momentum",
                "source_id": source.source_id,
                "value": Decimal("1.25"),
                "feature_version": "1.0.0",
                "params_hash": "old",
                "transform_type": "raw",
                "calc_timestamp": first_calc,
                "run_id": 1,
            }
        ],
    )
    inserted, updated = repo.upsert_batch(
        [
            {
                "instrument_id": instrument.instrument_id,
                "trade_date": trade_date,
                "feature_name": "momentum",
                "source_id": source.source_id,
                "value": Decimal("2.50"),
                "feature_version": "2.0.0",
                "params_hash": "new",
                "transform_type": "zscore",
                "calc_timestamp": second_calc,
                "run_id": 2,
            }
        ],
    )
    row = repo.get_by_key(instrument.instrument_id, trade_date, "momentum")

    assert (inserted, updated) == (0, 1)
    assert row.value == Decimal("2.500000")
    assert row.feature_version == "2.0.0"
    assert row.params_hash == "new"
    assert row.transform_type == "zscore"
    assert row.calc_timestamp == second_calc
    assert row.run_id == 2
