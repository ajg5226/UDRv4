"""Regression tests for the 5-year backfill script."""

from datetime import date

from scripts.backfill_5year import build_macro_record


def test_build_macro_record_uses_fred_obs_date_column():
    record = build_macro_record(
        {"obs_date": "2026-01-02", "value": 12.5},
        db_series_id=7,
        fred_source_id=3,
    )

    assert record == {
        "series_id": 7,
        "source_id": 3,
        "obs_date": date(2026, 1, 2),
        "value": 12.5,
    }


def test_build_macro_record_skips_missing_obs_date():
    assert build_macro_record({"date": "2026-01-02", "value": 12.5}, 7, 3) is None
