"""Repository regression tests for silent data corruption paths."""

from datetime import date, datetime

import pandas as pd

from atlas.storage.database import Database
from atlas.storage.models import DimInstrument, DimMacroSeries
from atlas.storage.repository import (
    FeatureRepository,
    InstrumentRepository,
    MacroRepository,
    MacroSeriesRepository,
    OHLCVRepository,
    SourceRepository,
)


def _create_database() -> Database:
    db = Database(connection_string="sqlite:///:memory:")
    db.create_tables()
    return db


def _seed_dimensions(session):
    source_repo = SourceRepository(session)
    instrument_repo = InstrumentRepository(session)
    series_repo = MacroSeriesRepository(session)

    source = source_repo.get_or_create("test-source", "test")
    instrument = instrument_repo.add(
        DimInstrument(ticker="ZERO", asset_type="equity", currency="USD")
    )
    series = series_repo.add(
        DimMacroSeries(fred_id="ZERO_RATE", name="Zero Rate", category="rates")
    )
    return source.source_id, instrument.instrument_id, series.series_id


def test_repository_readback_preserves_zero_values():
    db = _create_database()
    target_date = date(2026, 1, 2)

    with db.session() as session:
        source_id, instrument_id, series_id = _seed_dimensions(session)

        ohlcv_repo = OHLCVRepository(session)
        macro_repo = MacroRepository(session)
        feature_repo = FeatureRepository(session)

        ohlcv_repo.upsert_batch(
            [
                {
                    "instrument_id": instrument_id,
                    "trade_date": target_date,
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
                }
            ],
            source_id=source_id,
        )
        macro_repo.upsert_batch(
            [{"series_id": series_id, "obs_date": target_date, "value": 0}],
            source_id=source_id,
        )
        feature_repo.upsert_batch(
            [
                {
                    "instrument_id": instrument_id,
                    "trade_date": target_date,
                    "feature_name": "zero_feature",
                    "value": 0,
                }
            ]
        )

        ohlcv = ohlcv_repo.get_as_dataframe([instrument_id])
        macro = macro_repo.get_as_dataframe([series_id])
        features = feature_repo.get_features_for_date(target_date, instrument_ids=[instrument_id])

    assert ohlcv.loc[0, "open"] == 0.0
    assert ohlcv.loc[0, "adj_close"] == 0.0
    assert macro.loc[0, "value"] == 0.0
    assert features.loc[0, "zero_feature"] == 0.0


def test_ohlcv_sparse_update_does_not_clear_existing_values():
    db = _create_database()
    target_date = date(2026, 1, 2)

    with db.session() as session:
        source_id, instrument_id, _series_id = _seed_dimensions(session)
        repo = OHLCVRepository(session)

        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument_id,
                    "trade_date": target_date,
                    "open": 10,
                    "high": 11,
                    "low": 9,
                    "close": 10.5,
                    "volume": 100,
                    "adj_close": 10.4,
                }
            ],
            source_id=source_id,
        )
        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument_id,
                    "trade_date": target_date,
                    "open": None,
                    "high": float("nan"),
                    "low": 0,
                    "close": pd.NA,
                    "volume": 0,
                    "adj_close": None,
                }
            ],
            source_id=source_id,
        )

        row = repo.get_by_instrument_date(instrument_id, target_date)

    assert float(row.open) == 10.0
    assert float(row.high) == 11.0
    assert float(row.low) == 0.0
    assert float(row.close) == 10.5
    assert row.volume == 0
    assert float(row.adj_close) == 10.4


def test_empty_ohlcv_filter_returns_empty_dataframe_not_full_table():
    db = _create_database()

    with db.session() as session:
        source_id, instrument_id, _series_id = _seed_dimensions(session)
        repo = OHLCVRepository(session)
        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument_id,
                    "trade_date": date(2026, 1, 2),
                    "close": 10,
                }
            ],
            source_id=source_id,
        )

        result = repo.get_as_dataframe(instrument_ids=[])

    assert result.empty


def test_feature_upsert_refreshes_lineage_metadata():
    db = _create_database()
    target_date = date(2026, 1, 2)

    with db.session() as session:
        _source_id, instrument_id, _series_id = _seed_dimensions(session)
        repo = FeatureRepository(session)
        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument_id,
                    "trade_date": target_date,
                    "feature_name": "momentum",
                    "value": 1.0,
                    "feature_version": "v1",
                    "params_hash": "old",
                    "transform_type": "raw",
                    "calc_timestamp": datetime(2026, 1, 2, 1, 0),
                }
            ]
        )
        repo.upsert_batch(
            [
                {
                    "instrument_id": instrument_id,
                    "trade_date": target_date,
                    "feature_name": "momentum",
                    "value": 2.0,
                    "feature_version": "v2",
                    "params_hash": "new",
                    "transform_type": "zscore",
                    "calc_timestamp": datetime(2026, 1, 2, 2, 0),
                }
            ]
        )

        row = repo.get_by_key(instrument_id, target_date, "momentum")

    assert float(row.value) == 2.0
    assert row.feature_version == "v2"
    assert row.params_hash == "new"
    assert row.transform_type == "zscore"
    assert row.calc_timestamp == datetime(2026, 1, 2, 2, 0)
