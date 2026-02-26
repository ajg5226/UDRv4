"""Tests for atlas.features.transforms."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from atlas.features.schema import TransformType
from atlas.features.transforms import PanelTransformer, CrossSectionalStats


@pytest.fixture
def transformer():
    return PanelTransformer(winsorize_pct=0.025, zscore_clip=3.0)


@pytest.fixture
def sample_values():
    return pd.Series(
        {1: 10.0, 2: 20.0, 3: 30.0, 4: 40.0, 5: 50.0, 6: 60.0, 7: 70.0, 8: 80.0, 9: 90.0, 10: 100.0},
        name="test_feature",
    )


class TestRankTransform:
    def test_rank_range(self, transformer, sample_values):
        result = transformer.transform(sample_values, TransformType.RANK, "feat", date(2026, 1, 1))
        assert result.values.min() >= 0
        assert result.values.max() <= 100

    def test_rank_monotonic(self, transformer, sample_values):
        result = transformer.transform(sample_values, TransformType.RANK, "feat", date(2026, 1, 1))
        sorted_ids = sample_values.sort_values().index
        ranks = result.values[sorted_ids]
        assert all(ranks.iloc[i] <= ranks.iloc[i + 1] for i in range(len(ranks) - 1))

    def test_rank_preserves_nan(self, transformer):
        values = pd.Series({1: 10.0, 2: np.nan, 3: 30.0})
        result = transformer.transform(values, TransformType.RANK, "feat", date(2026, 1, 1))
        assert np.isnan(result.values[2])

    def test_rank_name(self, transformer, sample_values):
        result = transformer.transform(sample_values, TransformType.RANK, "feat", date(2026, 1, 1))
        assert result.feature_name == "feat_rank"


class TestZscoreTransform:
    def test_zscore_centered(self, transformer, sample_values):
        result = transformer.transform(sample_values, TransformType.ZSCORE, "feat", date(2026, 1, 1))
        assert abs(result.values.mean()) < 0.5

    def test_zscore_clipped(self, transformer):
        values = pd.Series({i: float(i) for i in range(100)})
        values[99] = 10000.0
        result = transformer.transform(values, TransformType.ZSCORE, "feat", date(2026, 1, 1))
        assert result.values.max() <= 3.0
        assert result.values.min() >= -3.0

    def test_zscore_constant_values(self, transformer):
        values = pd.Series({i: 5.0 for i in range(10)})
        result = transformer.transform(values, TransformType.ZSCORE, "feat", date(2026, 1, 1))
        assert (result.values == 0.0).all()


class TestQuintileTransform:
    def test_quintile_range(self, transformer, sample_values):
        result = transformer.transform(sample_values, TransformType.QUINTILE, "feat", date(2026, 1, 1))
        assert result.values.min() >= 1
        assert result.values.max() <= 5

    def test_quintile_name(self, transformer, sample_values):
        result = transformer.transform(sample_values, TransformType.QUINTILE, "feat", date(2026, 1, 1))
        assert result.feature_name == "feat_quintile"


class TestDecileTransform:
    def test_decile_range(self, transformer, sample_values):
        result = transformer.transform(sample_values, TransformType.DECILE, "feat", date(2026, 1, 1))
        assert result.values.min() >= 1
        assert result.values.max() <= 10


class TestRawTransform:
    def test_raw_returns_copy(self, transformer, sample_values):
        result = transformer.transform(sample_values, TransformType.RAW, "feat", date(2026, 1, 1))
        pd.testing.assert_series_equal(result.values, sample_values, check_names=False)
        assert result.feature_name == "feat"


class TestEdgeCases:
    def test_single_value(self, transformer):
        values = pd.Series({1: 42.0})
        result = transformer.transform(values, TransformType.RANK, "feat", date(2026, 1, 1))
        assert len(result.values) == 1

    def test_all_nan(self, transformer):
        values = pd.Series({1: np.nan, 2: np.nan})
        result = transformer.transform(values, TransformType.ZSCORE, "feat", date(2026, 1, 1))
        assert result.n_valid == 0

    def test_metadata_populated(self, transformer, sample_values):
        result = transformer.transform(sample_values, TransformType.RANK, "feat", date(2026, 1, 1))
        assert result.n_instruments == 10
        assert result.n_valid == 10
        assert result.raw_mean == pytest.approx(55.0)


class TestCrossSectionalStats:
    def test_dispersion(self):
        returns = pd.DataFrame({
            "A": [0.01, -0.02, 0.03],
            "B": [-0.01, 0.02, -0.03],
        })
        d = CrossSectionalStats.dispersion(returns)
        assert d > 0

    def test_average_correlation_to_benchmark(self):
        returns = pd.DataFrame({"A": [0.01, 0.02, 0.03], "B": [0.01, 0.02, 0.03]})
        benchmark = pd.Series([0.01, 0.02, 0.03])
        corr = CrossSectionalStats.average_correlation(returns, benchmark)
        assert corr == pytest.approx(1.0, abs=0.01)
