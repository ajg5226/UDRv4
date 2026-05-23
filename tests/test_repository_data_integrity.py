"""Regression tests for repository data-integrity behavior."""

from datetime import date

import numpy as np

from atlas.storage.database import Database
from atlas.storage.models import DimInstrument, DimSource
from atlas.storage.repository import OHLCVRepository


def test_ohlcv_sparse_update_preserves_existing_values_and_zeroes():
    db = Database(connection_string="sqlite:///:memory:")
    db.create_tables()

    with db.session() as session:
        source = DimSource(name="tiingo", provider_type="market_data")
        instrument = DimInstrument(ticker="ZERO", asset_type="equity")
        session.add_all([source, instrument])
        session.flush()

        repo = OHLCVRepository(session)
        trade_date = date(2026, 5, 22)

        inserted, updated = repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": trade_date,
                    "open": 0.0,
                    "high": 10.0,
                    "low": 0.0,
                    "close": 5.0,
                    "volume": 0,
                    "adj_open": 0.0,
                    "adj_high": 10.0,
                    "adj_low": 0.0,
                    "adj_close": 5.0,
                    "adj_volume": 0,
                }
            ],
            source_id=source.source_id,
        )

        assert (inserted, updated) == (1, 0)

        inserted, updated = repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": trade_date,
                    "open": None,
                    "high": np.nan,
                    "low": None,
                    "close": 6.0,
                    "volume": None,
                    "adj_open": None,
                    "adj_high": np.nan,
                    "adj_low": None,
                    "adj_close": 6.0,
                    "adj_volume": None,
                }
            ],
            source_id=source.source_id,
        )

        assert (inserted, updated) == (0, 1)

        row = repo.get_by_instrument_date(instrument.instrument_id, trade_date)
        assert float(row.open) == 0.0
        assert float(row.high) == 10.0
        assert float(row.low) == 0.0
        assert float(row.close) == 6.0
        assert row.volume == 0
        assert float(row.adj_open) == 0.0
        assert float(row.adj_high) == 10.0
        assert float(row.adj_low) == 0.0
        assert float(row.adj_close) == 6.0
        assert row.adj_volume == 0

        df = repo.get_as_dataframe([instrument.instrument_id], trade_date, trade_date)
        assert df.loc[0, "open"] == 0.0
        assert df.loc[0, "low"] == 0.0
        assert df.loc[0, "volume"] == 0
        assert df.loc[0, "close"] == 6.0
