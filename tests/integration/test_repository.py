"""Integration tests for atlas.storage.repository using in-memory SQLite."""

from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import pytest
from sqlalchemy.orm import Session

from atlas.storage.models import (
    DimInstrument,
    DimMacroSeries,
    DimSource,
    FactMacro,
    FactOHLCV,
    PipelineRun,
)
from atlas.storage.repository import (
    FeatureRepository,
    InstrumentRepository,
    MacroRepository,
    MacroSeriesRepository,
    OHLCVRepository,
    PipelineRunRepository,
    SourceRepository,
)


class TestSourceRepository:
    def test_get_or_create_new(self, db_session: Session):
        repo = SourceRepository(db_session)
        source = repo.get_or_create("tiingo", "market_data", "https://api.tiingo.com")
        assert source.source_id is not None
        assert source.name == "tiingo"

    def test_get_or_create_existing(self, db_session: Session):
        repo = SourceRepository(db_session)
        s1 = repo.get_or_create("tiingo", "market_data")
        s2 = repo.get_or_create("tiingo", "market_data")
        assert s1.source_id == s2.source_id

    def test_get_by_name(self, db_session: Session, sample_source):
        repo = SourceRepository(db_session)
        found = repo.get_by_name("test_provider")
        assert found is not None
        assert found.source_id == sample_source.source_id

    def test_get_active(self, db_session: Session, sample_source):
        repo = SourceRepository(db_session)
        active = repo.get_active()
        assert len(active) >= 1


class TestInstrumentRepository:
    def test_get_by_ticker(self, db_session: Session, sample_instruments):
        repo = InstrumentRepository(db_session)
        inst = repo.get_by_ticker("AAPL")
        assert inst is not None
        assert inst.ticker == "AAPL"
        assert inst.asset_type == "equity"

    def test_get_by_ticker_not_found(self, db_session: Session, sample_instruments):
        repo = InstrumentRepository(db_session)
        assert repo.get_by_ticker("ZZZZZ") is None

    def test_get_by_tickers(self, db_session: Session, sample_instruments):
        repo = InstrumentRepository(db_session)
        instruments = repo.get_by_tickers(["AAPL", "MSFT"])
        assert len(instruments) == 2

    def test_get_active(self, db_session: Session, sample_instruments):
        repo = InstrumentRepository(db_session)
        active = repo.get_active()
        assert len(active) == 3

    def test_add_and_get_tag(self, db_session: Session, sample_instruments):
        repo = InstrumentRepository(db_session)
        inst = sample_instruments[0]
        repo.add_tag(inst.instrument_id, "portfolio_main")
        tags = repo.get_tags(inst.instrument_id)
        assert "portfolio_main" in tags

    def test_remove_tag(self, db_session: Session, sample_instruments):
        repo = InstrumentRepository(db_session)
        inst = sample_instruments[0]
        repo.add_tag(inst.instrument_id, "watchlist")
        repo.remove_tag(inst.instrument_id, "watchlist")
        tags = repo.get_tags(inst.instrument_id)
        assert "watchlist" not in tags

    def test_get_by_tags(self, db_session: Session, sample_instruments):
        repo = InstrumentRepository(db_session)
        repo.add_tag(sample_instruments[0].instrument_id, "portfolio")
        repo.add_tag(sample_instruments[1].instrument_id, "portfolio")
        tagged = repo.get_by_tags(["portfolio"])
        assert len(tagged) == 2

    def test_duplicate_tag_ignored(self, db_session: Session, sample_instruments):
        repo = InstrumentRepository(db_session)
        inst = sample_instruments[0]
        repo.add_tag(inst.instrument_id, "tag1")
        repo.add_tag(inst.instrument_id, "tag1")
        tags = repo.get_tags(inst.instrument_id)
        assert tags.count("tag1") == 1

    def test_get_by_asset_type(self, db_session: Session, sample_instruments):
        repo = InstrumentRepository(db_session)
        etfs = repo.get_by_asset_type("etf")
        assert len(etfs) == 1
        assert etfs[0].ticker == "SPY"


class TestOHLCVRepository:
    def test_upsert_insert(self, db_session, sample_source, sample_instruments):
        repo = OHLCVRepository(db_session)
        records = [{
            "instrument_id": sample_instruments[0].instrument_id,
            "trade_date": date(2026, 1, 15),
            "open": 250.0, "high": 255.0, "low": 248.0, "close": 253.0,
            "volume": 1_000_000,
            "adj_close": 253.0, "adj_open": 250.0, "adj_high": 255.0,
            "adj_low": 248.0, "adj_volume": 1_000_000,
        }]
        inserted, updated = repo.upsert_batch(records, sample_source.source_id)
        assert inserted == 1
        assert updated == 0

    def test_upsert_update(self, db_session, sample_source, sample_instruments):
        repo = OHLCVRepository(db_session)
        record = {
            "instrument_id": sample_instruments[0].instrument_id,
            "trade_date": date(2026, 1, 15),
            "open": 250.0, "high": 255.0, "low": 248.0, "close": 253.0,
            "volume": 1_000_000,
            "adj_close": 253.0, "adj_open": 250.0, "adj_high": 255.0,
            "adj_low": 248.0, "adj_volume": 1_000_000,
        }
        repo.upsert_batch([record], sample_source.source_id)
        record["close"] = 260.0
        inserted, updated = repo.upsert_batch([record], sample_source.source_id)
        assert inserted == 0
        assert updated == 1

    def test_get_as_dataframe(self, db_session, sample_ohlcv_data, sample_instruments):
        repo = OHLCVRepository(db_session)
        df = repo.get_as_dataframe(
            instrument_ids=[sample_instruments[0].instrument_id],
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28),
        )
        assert not df.empty
        assert "adj_close" in df.columns
        assert "instrument_id" in df.columns

    def test_get_range(self, db_session, sample_ohlcv_data, sample_instruments):
        repo = OHLCVRepository(db_session)
        records = repo.get_range(
            sample_instruments[0].instrument_id,
            date(2026, 2, 1), date(2026, 2, 15),
        )
        assert len(records) > 0

    def test_empty_batch(self, db_session, sample_source):
        repo = OHLCVRepository(db_session)
        inserted, updated = repo.upsert_batch([], sample_source.source_id)
        assert inserted == 0
        assert updated == 0


class TestMacroRepository:
    def test_upsert_insert(self, db_session, sample_source, sample_macro_series):
        repo = MacroRepository(db_session)
        records = [{
            "series_id": sample_macro_series[0].series_id,
            "obs_date": date(2026, 2, 24),
            "value": 3.64,
        }]
        inserted, updated = repo.upsert_batch(records, sample_source.source_id)
        assert inserted == 1

    def test_upsert_update(self, db_session, sample_source, sample_macro_series):
        repo = MacroRepository(db_session)
        record = {
            "series_id": sample_macro_series[0].series_id,
            "obs_date": date(2026, 2, 24),
            "value": 3.64,
        }
        repo.upsert_batch([record], sample_source.source_id)
        record["value"] = 3.75
        inserted, updated = repo.upsert_batch([record], sample_source.source_id)
        assert updated == 1
        assert inserted == 0

    def test_get_as_dataframe(self, db_session, sample_source, sample_macro_series):
        repo = MacroRepository(db_session)
        repo.upsert_batch([{
            "series_id": sample_macro_series[0].series_id,
            "obs_date": date(2026, 2, 24),
            "value": 3.64,
        }], sample_source.source_id)
        df = repo.get_as_dataframe(series_ids=[sample_macro_series[0].series_id])
        assert len(df) == 1


class TestPipelineRunRepository:
    def test_create_run(self, db_session):
        repo = PipelineRunRepository(db_session)
        run = repo.create_run(
            run_type="manual",
            run_date=date(2026, 2, 24),
            providers=["fred"],
        )
        assert run.run_id is not None
        assert run.status == "running"
        assert run.run_type == "manual"

    def test_complete_run(self, db_session):
        repo = PipelineRunRepository(db_session)
        run = repo.create_run(run_type="manual", run_date=date(2026, 2, 24))
        repo.complete_run(
            run_id=run.run_id,
            status="success",
            records_inserted=100,
            records_updated=5,
        )
        db_session.expire_all()
        updated = repo.get_by_id(run.run_id)
        assert updated.status == "success"
        assert updated.records_inserted == 100

    def test_get_latest_run(self, db_session):
        repo = PipelineRunRepository(db_session)
        repo.create_run(run_type="manual", run_date=date(2026, 2, 20))
        repo.create_run(run_type="manual", run_date=date(2026, 2, 24))
        latest = repo.get_latest_run()
        assert latest is not None
        assert latest.run_date == date(2026, 2, 24)

    def test_get_latest_run_by_type(self, db_session):
        repo = PipelineRunRepository(db_session)
        repo.create_run(run_type="manual", run_date=date(2026, 2, 20))
        repo.create_run(run_type="backfill", run_date=date(2026, 2, 24))
        latest = repo.get_latest_run(run_type="backfill")
        assert latest.run_type == "backfill"

    def test_auto_increment_run_id(self, db_session):
        repo = PipelineRunRepository(db_session)
        r1 = repo.create_run(run_type="manual", run_date=date(2026, 2, 20))
        r2 = repo.create_run(run_type="manual", run_date=date(2026, 2, 21))
        assert r2.run_id > r1.run_id


class TestFeatureRepository:
    def test_upsert_batch(self, db_session, sample_instruments):
        repo = FeatureRepository(db_session)
        records = [{
            "instrument_id": sample_instruments[0].instrument_id,
            "trade_date": date(2026, 2, 24),
            "feature_name": "daily_return",
            "value": 0.015,
        }]
        inserted, updated = repo.upsert_batch(records)
        assert inserted == 1

    def test_upsert_update(self, db_session, sample_instruments):
        repo = FeatureRepository(db_session)
        record = {
            "instrument_id": sample_instruments[0].instrument_id,
            "trade_date": date(2026, 2, 24),
            "feature_name": "daily_return",
            "value": 0.015,
        }
        repo.upsert_batch([record])
        record["value"] = 0.020
        inserted, updated = repo.upsert_batch([record])
        assert updated == 1
        assert inserted == 0
