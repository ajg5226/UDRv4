"""Regression tests for 5-year backfill row conversion."""

from datetime import date

import pandas as pd

from scripts.backfill_5year import build_macro_records


def test_build_macro_records_uses_fred_obs_date_column():
    df = pd.DataFrame(
        [
            {
                "fred_id": "DGS10",
                "obs_date": date(2026, 1, 2),
                "value": 4.25,
            }
        ]
    )

    records = build_macro_records(df, db_series_id=123, source_id=7)

    assert records == [
        {
            "series_id": 123,
            "source_id": 7,
            "obs_date": date(2026, 1, 2),
            "value": 4.25,
        }
    ]
