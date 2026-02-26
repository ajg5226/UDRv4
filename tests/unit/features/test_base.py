"""Tests for atlas.features.base feature implementations."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from atlas.features.base import (
    CumulativeReturn,
    DailyReturn,
    LogReturn,
    RealizedVolatility,
    RSI,
    SimpleMovingAverage,
)


def _make_price_data(instrument_id: int, prices: list[float], start_date: date = date(2026, 1, 1)):
    """Helper to build a DataFrame from a price series."""
    rows = []
    for i, p in enumerate(prices):
        from datetime import timedelta
        rows.append({
            "instrument_id": instrument_id,
            "trade_date": start_date + timedelta(days=i),
            "adj_close": p,
        })
    return pd.DataFrame(rows)


class TestDailyReturn:
    def test_positive_return(self):
        data = _make_price_data(1, [100.0, 110.0])
        feat = DailyReturn()
        result = feat.calculate(data, date(2026, 1, 2))
        assert result[1] == pytest.approx(0.1)

    def test_negative_return(self):
        data = _make_price_data(1, [100.0, 90.0])
        feat = DailyReturn()
        result = feat.calculate(data, date(2026, 1, 2))
        assert result[1] == pytest.approx(-0.1)

    def test_zero_price_returns_nan(self):
        data = _make_price_data(1, [0.0, 10.0])
        feat = DailyReturn()
        result = feat.calculate(data, date(2026, 1, 2))
        assert np.isnan(result[1])

    def test_insufficient_data_returns_nan(self):
        data = _make_price_data(1, [100.0])
        feat = DailyReturn()
        result = feat.calculate(data, date(2026, 1, 1))
        assert np.isnan(result[1])

    def test_properties(self):
        feat = DailyReturn()
        assert feat.name == "daily_return"
        assert feat.category == "returns"
        assert feat.lookback_days == 2
        assert feat.dependencies == ["adj_close"]


class TestLogReturn:
    def test_positive_return(self):
        data = _make_price_data(1, [100.0, 110.0])
        feat = LogReturn()
        result = feat.calculate(data, date(2026, 1, 2))
        assert result[1] == pytest.approx(np.log(1.1), abs=1e-6)

    def test_negative_return(self):
        data = _make_price_data(1, [100.0, 90.0])
        feat = LogReturn()
        result = feat.calculate(data, date(2026, 1, 2))
        assert result[1] == pytest.approx(np.log(0.9), abs=1e-6)

    def test_zero_price_returns_nan(self):
        data = _make_price_data(1, [0.0, 10.0])
        feat = LogReturn()
        result = feat.calculate(data, date(2026, 1, 2))
        assert np.isnan(result[1])

    def test_properties(self):
        feat = LogReturn()
        assert feat.name == "log_return"
        assert feat.category == "returns"


class TestCumulativeReturn:
    def test_5d_cumulative(self):
        prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0]
        data = _make_price_data(1, prices)
        feat = CumulativeReturn(window=5)
        result = feat.calculate(data, date(2026, 1, 7))
        expected = (106.0 - 101.0) / 101.0
        assert result[1] == pytest.approx(expected, abs=1e-6)

    def test_insufficient_data(self):
        prices = [100.0, 101.0, 102.0]
        data = _make_price_data(1, prices)
        feat = CumulativeReturn(window=5)
        result = feat.calculate(data, date(2026, 1, 3))
        assert np.isnan(result[1])

    def test_name_includes_window(self):
        assert CumulativeReturn(window=21).name == "cumulative_return_21d"
        assert CumulativeReturn(window=63).name == "cumulative_return_63d"

    def test_parameters(self):
        feat = CumulativeReturn(window=5)
        assert feat.get_parameters() == {"window": 5}


class TestRealizedVolatility:
    def test_returns_positive_value(self):
        rng = np.random.default_rng(42)
        prices = [100.0]
        for _ in range(30):
            prices.append(prices[-1] * (1 + rng.normal(0.0, 0.02)))
        data = _make_price_data(1, prices)
        feat = RealizedVolatility(window=21)
        result = feat.calculate(data, date(2026, 1, 31))
        assert not np.isnan(result[1])
        assert result[1] > 0

    def test_annualized_vs_non_annualized(self):
        rng = np.random.default_rng(42)
        prices = [100.0]
        for _ in range(30):
            prices.append(prices[-1] * (1 + rng.normal(0.0, 0.02)))
        data = _make_price_data(1, prices)

        annual = RealizedVolatility(window=21, annualize=True)
        raw = RealizedVolatility(window=21, annualize=False)

        r_annual = annual.calculate(data, date(2026, 1, 31))
        r_raw = raw.calculate(data, date(2026, 1, 31))

        assert r_annual[1] == pytest.approx(r_raw[1] * np.sqrt(252), rel=1e-6)

    def test_name_includes_window(self):
        assert RealizedVolatility(window=63).name == "realized_vol_63d"


class TestSimpleMovingAverage:
    def test_constant_prices(self):
        prices = [100.0] * 25
        data = _make_price_data(1, prices)
        feat = SimpleMovingAverage(window=20)
        result = feat.calculate(data, date(2026, 1, 25))
        assert result[1] == pytest.approx(100.0)

    def test_ascending_prices(self):
        prices = list(range(1, 26))
        data = _make_price_data(1, [float(p) for p in prices])
        feat = SimpleMovingAverage(window=20)
        result = feat.calculate(data, date(2026, 1, 25))
        expected = np.mean(prices[-20:])
        assert result[1] == pytest.approx(expected)

    def test_insufficient_data(self):
        prices = [100.0] * 5
        data = _make_price_data(1, prices)
        feat = SimpleMovingAverage(window=20)
        result = feat.calculate(data, date(2026, 1, 5))
        assert np.isnan(result[1])

    def test_name_includes_window(self):
        assert SimpleMovingAverage(window=50).name == "sma_50"
        assert SimpleMovingAverage(window=200).name == "sma_200"


class TestRSI:
    def test_all_gains_equals_100(self):
        prices = [float(100 + i) for i in range(20)]
        data = _make_price_data(1, prices)
        feat = RSI(window=14)
        result = feat.calculate(data, date(2026, 1, 20))
        assert result[1] == pytest.approx(100.0)

    def test_all_losses_equals_0(self):
        prices = [float(120 - i) for i in range(20)]
        data = _make_price_data(1, prices)
        feat = RSI(window=14)
        result = feat.calculate(data, date(2026, 1, 20))
        assert result[1] == pytest.approx(0.0)

    def test_bounded_0_100(self):
        rng = np.random.default_rng(42)
        prices = [100.0]
        for _ in range(25):
            prices.append(prices[-1] * (1 + rng.normal(0.0, 0.02)))
        data = _make_price_data(1, prices)
        feat = RSI(window=14)
        result = feat.calculate(data, date(2026, 1, 26))
        assert 0 <= result[1] <= 100

    def test_properties(self):
        feat = RSI(window=14)
        assert feat.name == "rsi_14"
        assert feat.category == "momentum"
        assert feat.lookback_days == 15


class TestBaseFeatureValidation:
    def test_validate_detects_all_nan(self):
        feat = DailyReturn()
        values = pd.Series([np.nan, np.nan, np.nan])
        is_valid, errors = feat.validate(values)
        assert not is_valid
        assert len(errors) > 0

    def test_validate_detects_inf(self):
        feat = DailyReturn()
        values = pd.Series([1.0, np.inf, -np.inf])
        is_valid, errors = feat.validate(values)
        assert not is_valid

    def test_validate_passes_normal_values(self):
        feat = DailyReturn()
        values = pd.Series([0.01, -0.02, 0.005])
        is_valid, errors = feat.validate(values)
        assert is_valid
        assert len(errors) == 0


class TestMultipleInstruments:
    def test_daily_return_multiple_instruments(self):
        data1 = _make_price_data(1, [100.0, 110.0])
        data2 = _make_price_data(2, [200.0, 190.0])
        combined = pd.concat([data1, data2], ignore_index=True)

        feat = DailyReturn()
        result = feat.calculate(combined, date(2026, 1, 2))
        assert result[1] == pytest.approx(0.1)
        assert result[2] == pytest.approx(-0.05)
