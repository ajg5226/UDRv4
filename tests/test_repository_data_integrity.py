"""Regression tests for repository read/write data integrity."""

from datetime import date, datetime

from atlas.storage.database import Database
from atlas.storage.models import DimInstrument
from atlas.storage.repository import (
    FeatureRepository,
    InstrumentRepository,
    MacroRepository,
    MacroSeriesRepository,
    OHLCVRepository,
    SourceRepository,
)


def _memory_database() -> Database:
    db = Database("sqlite:///:memory:")
    db.create_tables()
    return db


def test_ohlcv_update_does_not_overwrite_existing_values_with_missing_data() -> None:
    db = _memory_database()

    with db.session() as session:
        source = SourceRepository(session).get_or_create("tiingo", "market_data")
        instrument = InstrumentRepository(session).add(
            DimInstrument(ticker="SPY", asset_type="equity")
        )
        repo = OHLCVRepository(session)
        trade_date = date(2026, 5, 22)

        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": trade_date,
                    "open": 100.0,
                    "high": 110.0,
                    "low": 95.0,
                    "close": 105.0,
                    "volume": 1000,
                    "adj_open": 100.0,
                    "adj_high": 110.0,
                    "adj_low": 95.0,
                    "adj_close": 105.0,
                    "adj_volume": 1000,
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
                    "low": 94.0,
                    "close": 0.0,
                    "volume": 0,
                }
            ],
            source.source_id,
        )

        row = repo.get_by_instrument_date(instrument.instrument_id, trade_date)
        assert row is not None
        assert float(row.open) == 100.0
        assert float(row.high) == 110.0
        assert float(row.low) == 94.0
        assert float(row.close) == 0.0
        assert row.volume == 0


def test_repository_dataframe_readback_preserves_zero_values() -> None:
    db = _memory_database()

    with db.session() as session:
        source_repo = SourceRepository(session)
        source = source_repo.get_or_create("tiingo", "market_data")
        fred_source = source_repo.get_or_create("fred", "macro")
        instrument = InstrumentRepository(session).add(
            DimInstrument(ticker="ZERO", asset_type="equity")
        )
        series = MacroSeriesRepository(session).get_or_create(
            fred_id="ZERO_SERIES",
            name="Zero Series",
            category="growth",
        )
        trade_date = date(2026, 5, 22)

        OHLCVRepository(session).upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": trade_date,
                    "open": 0.0,
                    "high": 0.0,
                    "low": 0.0,
                    "close": 0.0,
                    "volume": 0,
                    "adj_open": 0.0,
                    "adj_high": 0.0,
                    "adj_low": 0.0,
                    "adj_close": 0.0,
                    "adj_volume": 0,
                }
            ],
            source.source_id,
        )
        MacroRepository(session).upsert_batch(
            [
                {
                    "series_id": series.series_id,
                    "obs_date": trade_date,
                    "value": 0.0,
                }
            ],
            fred_source.source_id,
        )
        FeatureRepository(session).upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": trade_date,
                    "feature_name": "zero_feature",
                    "value": 0.0,
                }
            ]
        )

        ohlcv_df = OHLCVRepository(session).get_as_dataframe()
        macro_df = MacroRepository(session).get_as_dataframe()
        feature_df = FeatureRepository(session).get_features_for_date(trade_date)

        assert ohlcv_df.loc[0, "open"] == 0.0
        assert ohlcv_df.loc[0, "close"] == 0.0
        assert macro_df.loc[0, "value"] == 0.0
        assert feature_df.loc[0, "zero_feature"] == 0.0


def test_feature_upsert_refreshes_lineage_metadata() -> None:
    db = _memory_database()

    with db.session() as session:
        instrument = InstrumentRepository(session).add(
            DimInstrument(ticker="META", asset_type="equity")
        )
        repo = FeatureRepository(session)
        trade_date = date(2026, 5, 22)

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
                    "calc_timestamp": datetime(2026, 5, 22, 1, 0, 0),
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
                    "calc_timestamp": datetime(2026, 5, 22, 2, 0, 0),
                }
            ],
            run_id=2,
        )

        row = repo.get_by_key(instrument.instrument_id, trade_date, "momentum")
        assert row is not None
        assert float(row.value) == 2.0
        assert row.feature_version == "2.0.0"
        assert row.params_hash == "new"
        assert row.transform_type == "zscore"
        assert row.calc_timestamp == datetime(2026, 5, 22, 2, 0, 0)
        assert row.run_id == 2
