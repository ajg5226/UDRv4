"""Regression tests for repository data integrity behavior."""

from collections.abc import Generator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from atlas.storage.models import Base, DimInstrument, DimMacroSeries, DimSource, FactFeature
from atlas.storage.repository import FeatureRepository, MacroRepository, OHLCVRepository


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        yield session

    engine.dispose()


def test_ohlcv_partial_update_preserves_existing_values() -> None:
    with session_scope() as session:
        source = DimSource(name="tiingo", provider_type="market")
        instrument = DimInstrument(ticker="ABC", asset_type="equity")
        session.add_all([source, instrument])
        session.flush()

        repo = OHLCVRepository(session)
        trade_date = date(2026, 6, 12)
        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": trade_date,
                    "open": Decimal("10"),
                    "high": Decimal("11"),
                    "low": Decimal("9"),
                    "close": Decimal("10.5"),
                    "volume": 1000,
                    "adj_open": Decimal("10"),
                    "adj_high": Decimal("11"),
                    "adj_low": Decimal("9"),
                    "adj_close": Decimal("10.5"),
                    "adj_volume": 1000,
                }
            ],
            source_id=source.source_id,
        )

        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": trade_date,
                    "open": None,
                    "high": float("nan"),
                    "low": Decimal("0"),
                    "close": None,
                    "volume": None,
                    "adj_close": None,
                }
            ],
            source_id=source.source_id,
        )

        stored = repo.get_by_instrument_date(instrument.instrument_id, trade_date)
        assert stored is not None
        assert stored.open == Decimal("10")
        assert stored.high == Decimal("11")
        assert stored.low == Decimal("0")
        assert stored.close == Decimal("10.5")
        assert stored.volume == 1000
        assert stored.adj_close == Decimal("10.5")

        df = repo.get_as_dataframe([instrument.instrument_id], trade_date, trade_date)
        assert df.loc[0, "low"] == 0.0


def test_zero_macro_and_feature_values_are_preserved_in_dataframes() -> None:
    with session_scope() as session:
        source = DimSource(name="fred", provider_type="macro")
        instrument = DimInstrument(ticker="ABC", asset_type="equity")
        series = DimMacroSeries(fred_id="TEST", name="Test Series", category="growth")
        session.add_all([source, instrument, series])
        session.flush()

        obs_date = date(2026, 6, 12)
        macro_repo = MacroRepository(session)
        macro_repo.upsert_batch(
            [{"series_id": series.series_id, "obs_date": obs_date, "value": Decimal("0")}],
            source_id=source.source_id,
        )

        feature_repo = FeatureRepository(session)
        session.add(
            FactFeature(
                instrument_id=instrument.instrument_id,
                trade_date=obs_date,
                feature_name="zero_feature",
                source_id=source.source_id,
                value=Decimal("0"),
            )
        )
        session.flush()

        macro_df = macro_repo.get_as_dataframe([series.series_id], start_date=obs_date, end_date=obs_date)
        feature_df = feature_repo.get_features_for_date(obs_date, instrument_ids=[instrument.instrument_id])

        assert macro_df.loc[0, "value"] == 0.0
        assert feature_df.loc[0, "zero_feature"] == 0.0
