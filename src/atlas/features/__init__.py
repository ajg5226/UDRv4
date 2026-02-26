"""Feature engineering framework for derived analytics."""

# Schema - Single source of truth
from atlas.features.schema import (
    FeatureDefinition,
    FeatureFamily,
    HorizonFamily,
    TransformType,
    Directionality,
    DataRequirement,
    FEATURE_CATALOG,
    BENCHMARK_CONFIG,
    FACTOR_ETF_CONFIG,
    IC_HORIZONS,
    get_all_features,
    get_enabled_features,
    get_features_by_family,
    get_features_by_priority,
    get_feature,
    get_all_feature_variants,
    count_total_features,
)

# Generators
from atlas.features.generators import (
    BaseGenerator,
    MomentumGenerator,
    TrendGenerator,
    BreakoutGenerator,
    MeanReversionGenerator,
    FactorGenerator,
    RiskGenerator,
    UDRGenerator,
    RegimeGenerator,
    get_generator,
    GENERATORS,
)

# Transforms
from atlas.features.transforms import (
    PanelTransformer,
    TransformResult,
    CrossSectionalStats,
)

# Diagnostics
from atlas.features.diagnostics import (
    FeatureDiagnostic,
    DiagnosticsCalculator,
    DiagnosticsStore,
)

# Engine
from atlas.features.engine_v2 import (
    FeatureEngineV2,
    FeatureEngineConfig,
    EngineRunResult,
    calculate_features,
)

# Legacy (for backward compatibility)
from atlas.features.base import BaseFeature, FeatureResult
from atlas.features.registry import FeatureRegistry, get_feature_registry
from atlas.features.engine import FeatureEngine

__all__ = [
    # Schema
    "FeatureDefinition",
    "FeatureFamily",
    "HorizonFamily",
    "TransformType",
    "Directionality",
    "DataRequirement",
    "FEATURE_CATALOG",
    "BENCHMARK_CONFIG",
    "FACTOR_ETF_CONFIG",
    "IC_HORIZONS",
    "get_all_features",
    "get_enabled_features",
    "get_features_by_family",
    "get_features_by_priority",
    "get_feature",
    "get_all_feature_variants",
    "count_total_features",
    # Generators
    "BaseGenerator",
    "get_generator",
    "GENERATORS",
    # Transforms
    "PanelTransformer",
    "TransformResult",
    "CrossSectionalStats",
    # Diagnostics
    "FeatureDiagnostic",
    "DiagnosticsCalculator",
    "DiagnosticsStore",
    # Engine
    "FeatureEngineV2",
    "FeatureEngineConfig",
    "EngineRunResult",
    "calculate_features",
    # Legacy
    "BaseFeature",
    "FeatureResult",
    "FeatureRegistry",
    "get_feature_registry",
    "FeatureEngine",
]
