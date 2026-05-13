from datetime import date
from decimal import Decimal

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


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    return session_factory()


def test_ohlcv_upsert_does_not_clear_existing_values_with_missing_payload_fields():
    session = _session()
    source = DimSource(name="tiingo", provider_type="market_data")
    instrument = DimInstrument(ticker="SPY", asset_type="equity")
    session.add_all([source, instrument])
    session.flush()

    trade_date = date(2026, 5, 12)
    existing = FactOHLCV(
        instrument_id=instrument.instrument_id,
        trade_date=trade_date,
        source_id=source.source_id,
        close=Decimal("100.250000"),
        adj_close=Decimal("99.750000"),
        adj_open=Decimal("98.500000"),
    )
    session.add(existing)
    session.flush()

    inserted, updated = OHLCVRepository(session).upsert_batch(
        [
            {
                "instrument_id": instrument.instrument_id,
                "trade_date": trade_date,
                "close": Decimal("101.000000"),
                "adj_close": None,
                "adj_open": None,
            }
        ],
        source_id=source.source_id,
        run_id=42,
    )

    session.refresh(existing)
    assert (inserted, updated) == (0, 1)
    assert existing.close == Decimal("101.000000")
    assert existing.adj_close == Decimal("99.750000")
    assert existing.adj_open == Decimal("98.500000")
    assert existing.run_id == 42


def test_repository_dataframes_preserve_zero_numeric_values():
    session = _session()
    source = DimSource(name="test-source", provider_type="test")
    instrument = DimInstrument(ticker="ZERO", asset_type="equity")
    series = DimMacroSeries(fred_id="ZERO_SERIES", name="Zero Series", category="growth")
    session.add_all([source, instrument, series])
    session.flush()

    trade_date = date(2026, 5, 12)
    session.add_all(
        [
            FactOHLCV(
                instrument_id=instrument.instrument_id,
                trade_date=trade_date,
                source_id=source.source_id,
                close=Decimal("0.000000"),
                adj_close=Decimal("0.000000"),
            ),
            FactMacro(
                series_id=series.series_id,
                obs_date=trade_date,
                source_id=source.source_id,
                value=Decimal("0.000000"),
            ),
            FactFeature(
                instrument_id=instrument.instrument_id,
                trade_date=trade_date,
                feature_name="zero_feature",
                value=Decimal("0.000000"),
            ),
        ]
    )
    session.flush()

    ohlcv_df = OHLCVRepository(session).get_as_dataframe()
    macro_df = MacroRepository(session).get_as_dataframe()
    feature_df = FeatureRepository(session).get_features_for_date(trade_date)

    assert ohlcv_df.loc[0, "close"] == 0.0
    assert ohlcv_df.loc[0, "adj_close"] == 0.0
    assert macro_df.loc[0, "value"] == 0.0
    assert feature_df.loc[0, "zero_feature"] == 0.0
