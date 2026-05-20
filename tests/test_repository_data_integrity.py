from datetime import date
from decimal import Decimal

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

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


def make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    return session_factory()


def test_ohlcv_upsert_preserves_existing_values_when_update_is_sparse() -> None:
    with make_session() as session:
        source = DimSource(name="tiingo", provider_type="ohlcv")
        instrument = DimInstrument(ticker="AAPL", asset_type="equity")
        session.add_all([source, instrument])
        session.flush()

        repo = OHLCVRepository(session)
        trade_date = date(2026, 5, 18)

        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": trade_date,
                    "open": 100.0,
                    "high": 110.0,
                    "low": 99.0,
                    "close": 105.0,
                    "volume": 1_000_000,
                    "adj_open": 100.0,
                    "adj_high": 110.0,
                    "adj_low": 99.0,
                    "adj_close": 105.0,
                    "adj_volume": 1_000_000,
                }
            ],
            source.source_id,
        )

        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": trade_date,
                    "open": None,
                    "high": float("nan"),
                    "low": pd.NA,
                    "close": 106.0,
                    "volume": None,
                    "adj_close": float("nan"),
                    "adj_volume": pd.NA,
                }
            ],
            source.source_id,
        )

        stored = session.get(
            FactOHLCV,
            {"instrument_id": instrument.instrument_id, "trade_date": trade_date},
        )

        assert stored is not None
        assert float(stored.open) == 100.0
        assert float(stored.high) == 110.0
        assert float(stored.low) == 99.0
        assert float(stored.close) == 106.0
        assert stored.volume == 1_000_000
        assert float(stored.adj_close) == 105.0
        assert stored.adj_volume == 1_000_000


def test_repository_dataframes_preserve_zero_values() -> None:
    with make_session() as session:
        source = DimSource(name="test-source", provider_type="test")
        instrument = DimInstrument(ticker="ZERO", asset_type="equity")
        macro_series = DimMacroSeries(fred_id="ZERO", name="Zero Series", category="rates")
        session.add_all([source, instrument, macro_series])
        session.flush()

        trade_date = date(2026, 5, 18)
        session.add(
            FactOHLCV(
                instrument_id=instrument.instrument_id,
                trade_date=trade_date,
                source_id=source.source_id,
                open=Decimal("0"),
                high=Decimal("0"),
                low=Decimal("0"),
                close=Decimal("0"),
                adj_open=Decimal("0"),
                adj_high=Decimal("0"),
                adj_low=Decimal("0"),
                adj_close=Decimal("0"),
            )
        )
        session.add(
            FactMacro(
                series_id=macro_series.series_id,
                obs_date=trade_date,
                source_id=source.source_id,
                value=Decimal("0"),
            )
        )
        session.add(
            FactFeature(
                instrument_id=instrument.instrument_id,
                trade_date=trade_date,
                feature_name="zero_feature",
                value=Decimal("0"),
            )
        )
        session.flush()

        ohlcv_df = OHLCVRepository(session).get_as_dataframe()
        macro_df = MacroRepository(session).get_as_dataframe()
        feature_df = FeatureRepository(session).get_features_for_date(trade_date)

        assert ohlcv_df.loc[0, "open"] == 0.0
        assert ohlcv_df.loc[0, "close"] == 0.0
        assert macro_df.loc[0, "value"] == 0.0
        assert feature_df.loc[0, "zero_feature"] == 0.0
