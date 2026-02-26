"""Tests for atlas.features.generators."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from atlas.features.generators import (
    MomentumGenerator,
    TrendGenerator,
    BreakoutGenerator,
    MeanReversionGenerator,
    RiskGenerator,
    get_generator,
)
from atlas.features.schema import (
    FeatureDefinition,
    FeatureFamily,
    HorizonFamily,
    TransformType,
    DataRequirement,
    get_feature,
)


@pytest.fixture
def price_data():
    """Generate 500 calendar days of price data for 3 instruments (~350 trading days)."""
    rng = np.random.default_rng(42)
    rows = []
    base_date = date(2024, 9, 1)
    for inst_id in [1, 2, 3]:
        price = 100.0 + inst_id * 50
        for i in range(500):
            d = base_date + timedelta(days=i)
            if d.weekday() >= 5:
                continue
            ret = rng.normal(0.0005, 0.015)
            price *= 1 + ret
            rows.append({
                "instrument_id": inst_id,
                "trade_date": d,
                "adj_close": price,
                "high": price * 1.01,
                "low": price * 0.99,
                "close": price,
                "open": price * 0.999,
                "volume": 1_000_000,
            })
    return pd.DataFrame(rows)


@pytest.fixture
def target(price_data):
    """Use the last trading day in the dataset as target."""
    return price_data["trade_date"].max()


class TestMomentumGenerator:
    def test_mom_ts(self, price_data, target):
        gen = MomentumGenerator()
        feat = get_feature("mom_ts")
        result = gen.calculate(feat, price_data, 21, target)
        assert len(result.dropna()) > 0
        assert all(np.isfinite(v) for v in result.dropna())

    def test_mom_risk_adj(self, price_data, target):
        gen = MomentumGenerator()
        feat = get_feature("mom_risk_adj")
        result = gen.calculate(feat, price_data, 21, target)
        assert len(result.dropna()) > 0

    def test_family_property(self):
        gen = MomentumGenerator()
        assert gen.family == FeatureFamily.MOMENTUM


class TestTrendGenerator:
    def test_trend_slope(self, price_data, target):
        gen = TrendGenerator()
        feat = get_feature("trend_slope")
        result = gen.calculate(feat, price_data, 21, target)
        assert len(result.dropna()) > 0

    def test_trend_adx(self, price_data, target):
        gen = TrendGenerator()
        feat = get_feature("trend_adx")
        result = gen.calculate(feat, price_data, 14, target)
        assert len(result.dropna()) > 0

    def test_trend_efficiency(self, price_data, target):
        gen = TrendGenerator()
        feat = get_feature("trend_efficiency")
        result = gen.calculate(feat, price_data, 21, target)
        for v in result.dropna():
            assert -1.0 <= v <= 1.0 or np.isnan(v)


class TestBreakoutGenerator:
    def test_breakout_high_binary(self, price_data, target):
        gen = BreakoutGenerator()
        feat = get_feature("breakout_high")
        result = gen.calculate(feat, price_data, 20, target)
        for v in result.dropna():
            assert v in (0.0, 1.0)

    def test_breakout_dist_high(self, price_data, target):
        gen = BreakoutGenerator()
        feat = get_feature("breakout_dist_high")
        result = gen.calculate(feat, price_data, 20, target)
        assert len(result.dropna()) > 0


class TestMeanReversionGenerator:
    def test_mr_zscore(self, price_data, target):
        gen = MeanReversionGenerator()
        feat = get_feature("mr_zscore")
        result = gen.calculate(feat, price_data, 20, target)
        assert len(result.dropna()) > 0

    def test_mr_reversal(self, price_data, target):
        gen = MeanReversionGenerator()
        feat = get_feature("mr_reversal")
        result = gen.calculate(feat, price_data, 5, target)
        assert len(result.dropna()) > 0

    def test_mr_rsi_bounded(self, price_data, target):
        gen = MeanReversionGenerator()
        feat = get_feature("mr_rsi")
        result = gen.calculate(feat, price_data, 14, target)
        for v in result.dropna():
            assert 0 <= v <= 100


class TestRiskGenerator:
    def test_risk_realized_vol(self, price_data, target):
        gen = RiskGenerator()
        feat = get_feature("risk_realized_vol")
        result = gen.calculate(feat, price_data, 21, target)
        for v in result.dropna():
            assert v > 0

    def test_risk_drawdown_negative(self, price_data, target):
        gen = RiskGenerator()
        feat = get_feature("risk_drawdown")
        result = gen.calculate(feat, price_data, 63, target)
        for v in result.dropna():
            assert v <= 0


class TestGetGenerator:
    def test_all_families_have_generators(self):
        for family in [FeatureFamily.MOMENTUM, FeatureFamily.TREND,
                       FeatureFamily.BREAKOUT, FeatureFamily.MEAN_REVERSION,
                       FeatureFamily.RISK]:
            gen = get_generator(family)
            assert gen is not None
            assert gen.family == family
