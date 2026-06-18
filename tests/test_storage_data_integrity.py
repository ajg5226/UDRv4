from datetime import date

import pandas as pd
import pytest

from atlas.storage.database import Database
from atlas.storage.models import DimInstrument, DimMacroSeries
from atlas.storage.repository import (
    FeatureRepository,
    MacroRepository,
    OHLCVRepository,
    SourceRepository,
)


@pytest.fixture()
def database(tmp_path):
    db = Database(connection_string=f"sqlite:///{tmp_path / 'atlas.db'}")
    db.create_tables()
    yield db
    db.close()


def _seed_source_and_instrument(session) -> tuple[int, int]:
    source = SourceRepository(session).get_or_create(
        name="tiingo",
        provider_type="market_data",
        base_url="",
    )
    instrument = DimInstrument(ticker="ZERO", asset_type="equity")
    session.add(instrument)
    session.flush()
    return source.source_id, instrument.instrument_id


def test_ohlcv_sparse_update_preserves_existing_values(database):
    trade_date = date(2026, 6, 18)

    with database.session() as session:
        source_id, instrument_id = _seed_source_and_instrument(session)
        repo = OHLCVRepository(session)

        inserted, updated = repo.upsert_batch(
            [
                {
                    "instrument_id": instrument_id,
                    "trade_date": trade_date,
                    "open": 10.5,
                    "high": 11.0,
                    "low": 10.0,
                    "close": 10.75,
                    "volume": 100,
                    "adj_open": 10.5,
                    "adj_high": 11.0,
                    "adj_low": 10.0,
                    "adj_close": 10.75,
                    "adj_volume": 100,
                    "dividend": 0,
                    "split_factor": 1,
                }
            ],
            source_id=source_id,
        )

        assert (inserted, updated) == (1, 0)

        inserted, updated = repo.upsert_batch(
            [
                {
                    "instrument_id": instrument_id,
                    "trade_date": trade_date,
                    "open": None,
                    "high": pd.NA,
                    "low": float("nan"),
                    "close": 12.0,
                    "volume": 0,
                    "adj_open": None,
                    "adj_high": None,
                    "adj_low": None,
                    "adj_close": 12.0,
                    "adj_volume": 0,
                    "dividend": None,
                    "split_factor": None,
                }
            ],
            source_id=source_id,
        )

        assert (inserted, updated) == (0, 1)

        record = repo.get_by_instrument_date(instrument_id, trade_date)
        assert record is not None
        assert float(record.open) == 10.5
        assert float(record.high) == 11.0
        assert float(record.low) == 10.0
        assert float(record.close) == 12.0
        assert record.volume == 0
        assert float(record.adj_open) == 10.5
        assert float(record.adj_close) == 12.0
        assert record.adj_volume == 0
        assert float(record.dividend) == 0.0
        assert float(record.split_factor) == 1.0


def test_repository_dataframes_preserve_zero_values(database):
    trade_date = date(2026, 6, 18)

    with database.session() as session:
        source_id, instrument_id = _seed_source_and_instrument(session)

        macro_series = DimMacroSeries(
            fred_id="ZERO_SERIES",
            name="Zero Series",
            category="test",
        )
        session.add(macro_series)
        session.flush()

        ohlcv_repo = OHLCVRepository(session)
        ohlcv_repo.upsert_batch(
            [
                {
                    "instrument_id": instrument_id,
                    "trade_date": trade_date,
                    "open": 0,
                    "high": 0,
                    "low": 0,
                    "close": 0,
                    "volume": 0,
                    "adj_open": 0,
                    "adj_high": 0,
                    "adj_low": 0,
                    "adj_close": 0,
                    "adj_volume": 0,
                    "dividend": 0,
                    "split_factor": 0,
                }
            ],
            source_id=source_id,
        )

        macro_repo = MacroRepository(session)
        macro_repo.upsert_batch(
            [
                {
                    "series_id": macro_series.series_id,
                    "obs_date": trade_date,
                    "value": 0,
                }
            ],
            source_id=source_id,
        )

        feature_repo = FeatureRepository(session)
        feature_repo.upsert_batch(
            [
                {
                    "instrument_id": instrument_id,
                    "trade_date": trade_date,
                    "feature_name": "zero_feature",
                    "source_id": source_id,
                    "value": 0,
                }
            ]
        )

        ohlcv_df = ohlcv_repo.get_as_dataframe(
            instrument_ids=[instrument_id],
            start_date=trade_date,
            end_date=trade_date,
        )
        macro_df = macro_repo.get_as_dataframe(
            series_ids=[macro_series.series_id],
            start_date=trade_date,
            end_date=trade_date,
        )
        feature_df = feature_repo.get_features_for_date(
            trade_date=trade_date,
            instrument_ids=[instrument_id],
        )

    assert ohlcv_df.loc[0, "open"] == 0.0
    assert ohlcv_df.loc[0, "close"] == 0.0
    assert ohlcv_df.loc[0, "adj_close"] == 0.0
    assert ohlcv_df.loc[0, "volume"] == 0
    assert macro_df.loc[0, "value"] == 0.0
    assert feature_df.loc[0, "zero_feature"] == 0.0
