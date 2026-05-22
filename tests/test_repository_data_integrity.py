from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from atlas.storage.models import Base, DimInstrument, DimSource, FactOHLCV
from atlas.storage.repository import OHLCVRepository


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed_dimensions(session: Session) -> tuple[int, int]:
    source = DimSource(name="tiingo", provider_type="market_data")
    instrument = DimInstrument(ticker="SPY", exchange="NYSEARCA", asset_type="etf")
    session.add_all([source, instrument])
    session.flush()
    return instrument.instrument_id, source.source_id


def test_sparse_ohlcv_update_preserves_existing_non_null_values() -> None:
    with _session() as session:
        instrument_id, source_id = _seed_dimensions(session)
        repo = OHLCVRepository(session)
        trade_date = date(2026, 5, 21)

        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument_id,
                    "trade_date": trade_date,
                    "open": 100.0,
                    "high": 102.0,
                    "low": 99.0,
                    "close": 101.0,
                    "volume": 1_000,
                    "adj_open": 100.0,
                    "adj_high": 102.0,
                    "adj_low": 99.0,
                    "adj_close": 101.0,
                    "adj_volume": 1_000,
                }
            ],
            source_id=source_id,
        )

        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument_id,
                    "trade_date": trade_date,
                    "open": None,
                    "high": float("nan"),
                    "low": 98.5,
                    "close": None,
                    "volume": None,
                    "adj_open": None,
                    "adj_high": None,
                    "adj_low": 98.5,
                    "adj_close": None,
                    "adj_volume": None,
                }
            ],
            source_id=source_id,
        )

        stored = repo.get_by_instrument_date(instrument_id, trade_date)
        assert stored is not None
        assert float(stored.open) == 100.0
        assert float(stored.high) == 102.0
        assert float(stored.low) == 98.5
        assert float(stored.close) == 101.0
        assert stored.volume == 1_000
        assert float(stored.adj_close) == 101.0
        assert stored.adj_volume == 1_000


def test_ohlcv_dataframe_preserves_legitimate_zero_values() -> None:
    with _session() as session:
        instrument_id, source_id = _seed_dimensions(session)
        trade_date = date(2026, 5, 21)
        session.add(
            FactOHLCV(
                instrument_id=instrument_id,
                trade_date=trade_date,
                source_id=source_id,
                open=0,
                high=0,
                low=0,
                close=0,
                volume=0,
                adj_open=0,
                adj_high=0,
                adj_low=0,
                adj_close=0,
                adj_volume=0,
            )
        )
        session.flush()

        df = OHLCVRepository(session).get_as_dataframe(
            instrument_ids=[instrument_id],
            start_date=trade_date,
            end_date=trade_date,
        )

        assert df.loc[0, "open"] == 0.0
        assert df.loc[0, "high"] == 0.0
        assert df.loc[0, "low"] == 0.0
        assert df.loc[0, "close"] == 0.0
        assert df.loc[0, "adj_close"] == 0.0
        assert df.loc[0, "volume"] == 0
        assert df.loc[0, "adj_volume"] == 0
