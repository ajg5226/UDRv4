"""Tests for atlas.features.schema."""

import pytest

from atlas.features.schema import (
    FEATURE_CATALOG,
    FeatureDefinition,
    FeatureFamily,
    TransformType,
    Directionality,
    DataRequirement,
    HorizonFamily,
    get_all_features,
    get_enabled_features,
    get_features_by_family,
    get_features_by_priority,
    get_feature,
    get_all_feature_variants,
    count_total_features,
    BENCHMARK_CONFIG,
    FACTOR_ETF_CONFIG,
)


class TestFeatureCatalog:
    def test_catalog_not_empty(self):
        assert len(FEATURE_CATALOG) > 0

    def test_all_features_have_required_fields(self):
        for name, feat in FEATURE_CATALOG.items():
            assert feat.name == name
            assert isinstance(feat.family, FeatureFamily)
            assert feat.description
            assert feat.lookback_days > 0
            assert feat.min_history > 0

    def test_known_features_exist(self):
        expected = ["mom_ts", "trend_slope", "breakout_high", "mr_zscore",
                     "factor_beta_spy", "risk_realized_vol", "udr_up_capture",
                     "regime_hurst"]
        for name in expected:
            assert name in FEATURE_CATALOG, f"Missing feature: {name}"


class TestFeatureDefinition:
    def test_get_full_name_raw(self):
        feat = FeatureDefinition(
            name="test", family=FeatureFamily.MOMENTUM, description="Test",
            horizon_family=HorizonFamily.FAST, lookback_days=21, min_history=63,
        )
        assert feat.get_full_name(21, TransformType.RAW) == "test_21d"

    def test_get_full_name_with_transform(self):
        feat = FeatureDefinition(
            name="test", family=FeatureFamily.MOMENTUM, description="Test",
            horizon_family=HorizonFamily.FAST, lookback_days=21, min_history=63,
        )
        assert feat.get_full_name(21, TransformType.RANK) == "test_21d_rank"
        assert feat.get_full_name(21, TransformType.ZSCORE) == "test_21d_zscore"

    def test_generate_variants(self):
        feat = FeatureDefinition(
            name="test", family=FeatureFamily.MOMENTUM, description="Test",
            horizon_family=HorizonFamily.MULTI, lookback_days=21, min_history=63,
            lookback_variants=[21, 63],
            transforms=[TransformType.RAW, TransformType.RANK],
        )
        variants = feat.generate_variants()
        assert len(variants) == 4  # 2 lookbacks × 2 transforms
        names = [v[0] for v in variants]
        assert "test_21d" in names
        assert "test_63d_rank" in names

    def test_generate_variants_no_lookback_variants(self):
        feat = FeatureDefinition(
            name="test", family=FeatureFamily.MOMENTUM, description="Test",
            horizon_family=HorizonFamily.FAST, lookback_days=14, min_history=63,
            transforms=[TransformType.RAW],
        )
        variants = feat.generate_variants()
        assert len(variants) == 1


class TestQueryFunctions:
    def test_get_all_features(self):
        all_feats = get_all_features()
        assert len(all_feats) == len(FEATURE_CATALOG)

    def test_get_enabled_features(self):
        enabled = get_enabled_features()
        assert all(f.enabled for f in enabled)

    def test_get_features_by_family(self):
        momentum = get_features_by_family(FeatureFamily.MOMENTUM)
        assert all(f.family == FeatureFamily.MOMENTUM for f in momentum)
        assert len(momentum) >= 2

    def test_get_features_by_priority(self):
        p1 = get_features_by_priority(max_priority=1)
        p2 = get_features_by_priority(max_priority=2)
        assert len(p2) >= len(p1)
        assert all(f.priority <= 1 for f in p1)

    def test_get_feature_by_name(self):
        feat = get_feature("mom_ts")
        assert feat is not None
        assert feat.name == "mom_ts"

    def test_get_feature_nonexistent(self):
        assert get_feature("nonexistent") is None

    def test_count_total_features(self):
        counts = count_total_features()
        assert "total" in counts
        assert counts["total"] > 0

    def test_get_all_feature_variants(self):
        variants = get_all_feature_variants()
        assert len(variants) > 0
        full_name, defn, lookback, transform = variants[0]
        assert isinstance(full_name, str)
        assert isinstance(defn, FeatureDefinition)


class TestConstants:
    def test_benchmark_config(self):
        assert BENCHMARK_CONFIG["primary"] == "SPY"

    def test_factor_etf_config(self):
        assert "momentum" in FACTOR_ETF_CONFIG
        assert FACTOR_ETF_CONFIG["momentum"] == "MTUM"
        assert "quality" in FACTOR_ETF_CONFIG
