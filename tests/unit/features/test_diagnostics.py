"""Tests for atlas.features.diagnostics."""

import numpy as np
import pandas as pd
import pytest

from atlas.features.diagnostics import DiagnosticsCalculator


@pytest.fixture
def calculator():
    return DiagnosticsCalculator(horizons=[5, 21], min_observations=5)


class TestCalculateIC:
    def test_perfect_positive_correlation(self, calculator):
        features = pd.Series({1: 1.0, 2: 2.0, 3: 3.0, 4: 4.0, 5: 5.0})
        returns = pd.Series({1: 0.01, 2: 0.02, 3: 0.03, 4: 0.04, 5: 0.05})
        ic_s, ic_p, t, n = calculator.calculate_ic(features, returns)
        assert ic_s == pytest.approx(1.0, abs=0.01)
        assert n == 5

    def test_perfect_negative_correlation(self, calculator):
        features = pd.Series({1: 5.0, 2: 4.0, 3: 3.0, 4: 2.0, 5: 1.0})
        returns = pd.Series({1: 0.01, 2: 0.02, 3: 0.03, 4: 0.04, 5: 0.05})
        ic_s, ic_p, t, n = calculator.calculate_ic(features, returns)
        assert ic_s == pytest.approx(-1.0, abs=0.01)

    def test_insufficient_observations(self, calculator):
        features = pd.Series({1: 1.0, 2: 2.0})
        returns = pd.Series({1: 0.01, 2: 0.02})
        ic_s, ic_p, t, n = calculator.calculate_ic(features, returns)
        assert np.isnan(ic_s)
        assert n == 2

    def test_handles_nan_in_data(self, calculator):
        features = pd.Series({1: 1.0, 2: np.nan, 3: 3.0, 4: 4.0, 5: 5.0, 6: 6.0})
        returns = pd.Series({1: 0.01, 2: 0.02, 3: 0.03, 4: 0.04, 5: 0.05, 6: 0.06})
        ic_s, ic_p, t, n = calculator.calculate_ic(features, returns)
        assert n == 5


class TestCalculateHitRate:
    def test_perfect_hit_rate(self, calculator):
        features = pd.Series({1: 1.0, 2: 2.0, 3: 3.0, 4: 4.0, 5: 5.0, 6: 6.0})
        returns = pd.Series({1: -0.03, 2: -0.02, 3: -0.01, 4: 0.01, 5: 0.02, 6: 0.03})
        hr = calculator.calculate_hit_rate(features, returns, "higher_better")
        assert hr >= 0.8

    def test_hit_rate_bounded_0_1(self, calculator):
        rng = np.random.default_rng(42)
        features = pd.Series({i: rng.standard_normal() for i in range(50)})
        returns = pd.Series({i: rng.standard_normal() * 0.01 for i in range(50)})
        hr = calculator.calculate_hit_rate(features, returns)
        assert 0 <= hr <= 1

    def test_insufficient_observations(self, calculator):
        features = pd.Series({1: 1.0, 2: 2.0})
        returns = pd.Series({1: 0.01, 2: 0.02})
        hr = calculator.calculate_hit_rate(features, returns)
        assert np.isnan(hr)


class TestFeatureDiagnostic:
    def test_is_significant(self):
        from atlas.features.diagnostics import FeatureDiagnostic
        from datetime import date
        d = FeatureDiagnostic("feat", "1.0", date(2026, 1, 1), 21, "all", t_stat=2.5)
        assert d.is_significant

    def test_not_significant(self):
        from atlas.features.diagnostics import FeatureDiagnostic
        from datetime import date
        d = FeatureDiagnostic("feat", "1.0", date(2026, 1, 1), 21, "all", t_stat=1.0)
        assert not d.is_significant

    def test_is_stable(self):
        from atlas.features.diagnostics import FeatureDiagnostic
        from datetime import date
        d = FeatureDiagnostic("feat", "1.0", date(2026, 1, 1), 21, "all", ic_ir=0.8)
        assert d.is_stable


class TestRollingICStats:
    def test_calculates_stats(self, calculator):
        ics = pd.Series([0.05, 0.03, 0.04, 0.02, 0.06, 0.01, 0.05, 0.03,
                         0.04, 0.02, 0.06, 0.01])
        stats = calculator.calculate_rolling_ic_stats("feat", ics)
        assert not np.isnan(stats["ic_mean"])
        assert not np.isnan(stats["ic_ir"])
        assert stats["ic_mean"] > 0

    def test_too_few_observations(self, calculator):
        ics = pd.Series([0.05, 0.03])
        stats = calculator.calculate_rolling_ic_stats("feat", ics)
        assert np.isnan(stats["ic_ir"])
