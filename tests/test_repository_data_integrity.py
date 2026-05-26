from datetime import date, datetime
from math import nan

import pytest

from atlas.storage.database import Database
from atlas.storage.models import DimInstrument, FactFeature
from atlas.storage.repository import (
    FeatureRepository,
    OHLCVRepository,
    SourceRepository,
)


@pytest.fixture
def session():
    db = Database("sqlite:///:memory:")
    db.create_tables()
    with db.session() as session:
        yield session


def test_ohlcv_sparse_update_does_not_clear_existing_values(session):
    source = SourceRepository(session).get_or_create("tiingo", "market")
    instrument = DimInstrument(ticker="ZERO", asset_type="equity")
    session.add(instrument)
    session.flush()

    repo = OHLCVRepository(session)
    repo.upsert_batch(
        [
            {
                "instrument_id": instrument.instrument_id,
                "trade_date": date(2026, 5, 26),
                "open": 0,
                "high": 10,
                "low": 1,
                "close": 5,
                "volume": 100,
                "adj_open": 0,
                "adj_high": 10,
                "adj_low": 1,
                "adj_close": 5,
                "adj_volume": 100,
            }
        ],
        source_id=source.source_id,
    )

    repo.upsert_batch(
        [
            {
                "instrument_id": instrument.instrument_id,
                "trade_date": date(2026, 5, 26),
                "open": None,
                "high": nan,
                "low": None,
                "close": 6,
                "volume": None,
                "adj_open": None,
                "adj_high": nan,
                "adj_low": None,
                "adj_close": 6,
                "adj_volume": None,
            }
        ],
        source_id=source.source_id,
    )

    row = repo.get_by_instrument_date(instrument.instrument_id, date(2026, 5, 26))
    assert float(row.open) == 0.0
    assert float(row.high) == 10.0
    assert float(row.low) == 1.0
    assert float(row.close) == 6.0
    assert row.volume == 100

    df = repo.get_as_dataframe([instrument.instrument_id])
    assert df.loc[0, "open"] == 0.0
    assert df.loc[0, "adj_open"] == 0.0


def test_feature_upsert_refreshes_lineage_metadata(session):
    source = SourceRepository(session).get_or_create("feature-engine", "features")
    instrument = DimInstrument(ticker="ABC", asset_type="equity")
    session.add(instrument)
    session.flush()

    repo = FeatureRepository(session)
    repo.upsert_batch(
        [
            {
                "instrument_id": instrument.instrument_id,
                "trade_date": date(2026, 5, 26),
                "feature_name": "mom_21",
                "source_id": source.source_id,
                "value": 0,
                "feature_version": "v1",
                "params_hash": "old",
                "transform_type": "raw",
                "calc_timestamp": datetime(2026, 5, 26, 1, 0),
            }
        ]
    )

    repo.upsert_batch(
        [
            {
                "instrument_id": instrument.instrument_id,
                "trade_date": date(2026, 5, 26),
                "feature_name": "mom_21",
                "source_id": source.source_id,
                "value": 1.25,
                "feature_version": "v2",
                "params_hash": "new",
                "transform_type": "zscore",
                "calc_timestamp": datetime(2026, 5, 26, 2, 0),
            }
        ]
    )

    row = session.get(FactFeature, (instrument.instrument_id, date(2026, 5, 26), "mom_21"))
    assert float(row.value) == 1.25
    assert row.feature_version == "v2"
    assert row.params_hash == "new"
    assert row.transform_type == "zscore"
    assert row.calc_timestamp == datetime(2026, 5, 26, 2, 0)

    df = repo.get_features_for_date(date(2026, 5, 26))
    assert df.loc[0, "mom_21"] == 1.25
