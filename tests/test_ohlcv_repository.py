from datetime import date

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from atlas.storage.models import Base, DimInstrument, DimSource, FactOHLCV
from atlas.storage.repository import OHLCVRepository


def test_upsert_batch_preserves_existing_values_when_update_is_sparse() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
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
