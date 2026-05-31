"""Regression tests for repository data-integrity edge cases."""

from datetime import date, datetime

import pytest

from atlas.storage.database import Database
from atlas.storage.models import DimInstrument
from atlas.storage.repository import (
    FeatureRepository,
    MacroRepository,
    MacroSeriesRepository,
    OHLCVRepository,
    SourceRepository,
)


@pytest.fixture()
def db():
    database = Database(connection_string="sqlite:///:memory:")
    database.create_tables()
    return database


def _create_source_and_instrument(session):
    source = SourceRepository(session).get_or_create(
        name="test",
        provider_type="test",
        base_url="https://example.test",
    )
    instrument = DimInstrument(ticker="ZERO", asset_type="equity", currency="USD")
    session.add(instrument)
    session.flush()
    return source, instrument


def test_ohlcv_sparse_update_preserves_existing_values_and_zero_readback(db):
    trade_date = date(2026, 1, 2)

    with db.session() as session:
        source, instrument = _create_source_and_instrument(session)
        repo = OHLCVRepository(session)

        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": trade_date,
                    "open": 0.0,
                    "high": 10.0,
                    "low": 0.0,
                    "close": 5.0,
                    "volume": 100,
                    "adj_open": 0.0,
                    "adj_high": 10.0,
                    "adj_low": 0.0,
                    "adj_close": 5.0,
                    "adj_volume": 100,
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
                    "high": None,
                    "low": None,
                    "close": None,
                    "volume": 200,
                    "adj_open": None,
                    "adj_high": None,
                    "adj_low": None,
                    "adj_close": None,
                    "adj_volume": 200,
                }
            ],
            source_id=source.source_id,
        )

        existing = repo.get_by_instrument_date(instrument.instrument_id, trade_date)
        assert float(existing.close) == 5.0
        assert float(existing.high) == 10.0
        assert existing.volume == 200

        df = repo.get_as_dataframe([instrument.instrument_id], trade_date, trade_date)
        row = df.iloc[0]
        assert row["open"] == 0.0
        assert row["low"] == 0.0
        assert row["adj_open"] == 0.0


def test_macro_zero_value_readback_preserves_zero(db):
    obs_date = date(2026, 1, 2)

    with db.session() as session:
        source = SourceRepository(session).get_or_create("fred", "macro")
        series = MacroSeriesRepository(session).get_or_create(
            fred_id="ZERO",
            name="Zero Series",
            category="test",
        )

        repo = MacroRepository(session)
        repo.upsert_batch(
            [{"series_id": series.series_id, "obs_date": obs_date, "value": 0.0}],
            source_id=source.source_id,
        )

        df = repo.get_as_dataframe([series.series_id], start_date=obs_date, end_date=obs_date)
        assert df.iloc[0]["value"] == 0.0


def test_feature_upsert_refreshes_value_and_lineage_metadata(db):
    trade_date = date(2026, 1, 2)

    with db.session() as session:
        _, instrument = _create_source_and_instrument(session)
        repo = FeatureRepository(session)

        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument.instrument_id,
                    "trade_date": trade_date,
                    "feature_name": "momentum",
                    "value": 1.0,
                    "feature_version": "v1",
                    "params_hash": "old",
                    "transform_type": "raw",
                    "calc_timestamp": datetime(2026, 1, 2, 12, 0, 0),
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
                    "feature_version": "v2",
                    "params_hash": "new",
                    "transform_type": "zscore",
                    "calc_timestamp": datetime(2026, 1, 3, 12, 0, 0),
                }
            ],
            run_id=2,
        )

        feature = repo.get_by_key(instrument.instrument_id, trade_date, "momentum")
        assert float(feature.value) == 2.0
        assert feature.feature_version == "v2"
        assert feature.params_hash == "new"
        assert feature.transform_type == "zscore"
        assert feature.run_id == 2
