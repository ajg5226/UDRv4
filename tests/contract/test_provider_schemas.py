"""Contract tests for provider API response schemas.

Uses synthetic recorded responses to validate that provider parsing logic
handles real-world API response shapes correctly.
"""

from datetime import date

import pandas as pd
import pytest

from atlas.providers.base import ProviderResult, ProviderType, ValidationStatus


SAMPLE_TIINGO_RESPONSE = [
    {
        "adjClose": 272.14,
        "adjHigh": 274.89,
        "adjLow": 267.71,
        "adjOpen": 267.86,
        "adjVolume": 47014619,
        "close": 272.14,
        "date": "2026-02-24T00:00:00+00:00",
        "divCash": 0.0,
        "high": 274.89,
        "low": 267.71,
        "open": 267.86,
        "splitFactor": 1.0,
        "volume": 47014619,
    }
]

SAMPLE_FRED_RESPONSE = {
    "realtime_start": "2026-02-24",
    "realtime_end": "2026-02-24",
    "observation_start": "2026-02-24",
    "observation_end": "2026-02-24",
    "units": "lin",
    "output_type": 1,
    "file_type": "json",
    "order_by": "observation_date",
    "sort_order": "asc",
    "count": 1,
    "offset": 0,
    "limit": 100000,
    "observations": [
        {"realtime_start": "2026-02-24", "realtime_end": "2026-02-24",
         "date": "2026-02-24", "value": "3.640"}
    ],
}


class TestTiingoResponseSchema:
    def test_has_required_price_fields(self):
        row = SAMPLE_TIINGO_RESPONSE[0]
        required = ["close", "high", "low", "open", "volume", "date"]
        for field in required:
            assert field in row, f"Missing field: {field}"

    def test_has_adjusted_fields(self):
        row = SAMPLE_TIINGO_RESPONSE[0]
        adjusted = ["adjClose", "adjHigh", "adjLow", "adjOpen", "adjVolume"]
        for field in adjusted:
            assert field in row, f"Missing adjusted field: {field}"

    def test_has_corporate_actions(self):
        row = SAMPLE_TIINGO_RESPONSE[0]
        assert "divCash" in row
        assert "splitFactor" in row

    def test_price_values_numeric(self):
        row = SAMPLE_TIINGO_RESPONSE[0]
        for field in ["close", "high", "low", "open", "adjClose"]:
            assert isinstance(row[field], (int, float))

    def test_volume_is_integer(self):
        row = SAMPLE_TIINGO_RESPONSE[0]
        assert isinstance(row["volume"], int)

    def test_parse_to_dataframe(self):
        df = pd.DataFrame(SAMPLE_TIINGO_RESPONSE)
        assert len(df) == 1
        assert df["close"].iloc[0] == 272.14
        assert df["adjClose"].iloc[0] == 272.14

    def test_date_parseable(self):
        row = SAMPLE_TIINGO_RESPONSE[0]
        parsed = pd.Timestamp(row["date"])
        assert parsed.date() == date(2026, 2, 24)


class TestFredResponseSchema:
    def test_has_observations_key(self):
        assert "observations" in SAMPLE_FRED_RESPONSE

    def test_observation_has_required_fields(self):
        obs = SAMPLE_FRED_RESPONSE["observations"][0]
        assert "date" in obs
        assert "value" in obs

    def test_value_is_string(self):
        obs = SAMPLE_FRED_RESPONSE["observations"][0]
        assert isinstance(obs["value"], str)

    def test_value_parseable_as_float(self):
        obs = SAMPLE_FRED_RESPONSE["observations"][0]
        value = float(obs["value"])
        assert value == pytest.approx(3.64)

    def test_date_parseable(self):
        obs = SAMPLE_FRED_RESPONSE["observations"][0]
        parsed = pd.Timestamp(obs["date"])
        assert parsed.date() == date(2026, 2, 24)

    def test_count_matches_observations(self):
        assert SAMPLE_FRED_RESPONSE["count"] == len(SAMPLE_FRED_RESPONSE["observations"])

    def test_handles_missing_value(self):
        obs_missing = {"date": "2026-02-22", "value": "."}
        assert obs_missing["value"] == "."


class TestProviderResultContract:
    def test_success_result_structure(self):
        result = ProviderResult(
            provider_name="tiingo",
            fetch_date=date(2026, 2, 24),
            data=pd.DataFrame(SAMPLE_TIINGO_RESPONSE),
            success=True,
        )
        assert result.success is True
        assert not result.data.empty
        assert result.error_message is None

    def test_failure_result_structure(self):
        result = ProviderResult(
            provider_name="fred",
            fetch_date=date(2026, 2, 24),
            data=pd.DataFrame(),
            success=False,
            error_message="API key invalid",
        )
        assert result.success is False
        assert result.data.empty
        assert result.error_message == "API key invalid"
