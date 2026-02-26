"""
Unified Feature Schema - Single Source of Truth

This module defines all features, their parameters, metadata, and generation rules.
All feature definitions flow from this schema - no parallel systems.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class HorizonFamily(str, Enum):
    """Feature horizon classification."""
    FAST = "fast"           # 5-21 days
    MEDIUM = "medium"       # 21-63 days
    SLOW = "slow"           # 63-252 days
    MULTI = "multi"         # Multiple horizons


class FeatureFamily(str, Enum):
    """Feature family classification."""
    MOMENTUM = "momentum"
    TREND = "trend"
    BREAKOUT = "breakout"
    MEAN_REVERSION = "mean_reversion"
    FACTOR = "factor"
    RISK = "risk"
    UDR = "udr"
    REGIME = "regime"


class TransformType(str, Enum):
    """Cross-sectional transformation types."""
    RAW = "raw"
    RANK = "rank"           # Percentile rank 0-100
    ZSCORE = "zscore"       # Winsorized then standardized
    QUINTILE = "quintile"   # 1-5 buckets
    DECILE = "decile"       # 1-10 buckets


class Directionality(str, Enum):
    """Signal directionality (higher value means...)."""
    HIGHER_BETTER = "higher_better"     # Long signal
    LOWER_BETTER = "lower_better"       # Short signal
    NEUTRAL = "neutral"                 # No directional interpretation


class DataRequirement(str, Enum):
    """Required input data types."""
    OHLCV = "ohlcv"
    BENCHMARK = "benchmark"
    FACTOR_ETFS = "factor_etfs"
    MACRO = "macro"
    FEATURES = "features"   # Depends on other features


@dataclass
class FeatureDefinition:
    """
    Complete definition of a feature.
    
    This is the canonical specification for any feature in the system.
    """
    # Identity
    name: str
    family: FeatureFamily
    description: str
    
    # Horizon and timing
    horizon_family: HorizonFamily
    lookback_days: int
    min_history: int  # Minimum days of data required
    
    # Parameters (for parameterized features)
    parameters: dict[str, Any] = field(default_factory=dict)
    lookback_variants: list[int] = field(default_factory=list)  # Auto-generate variants
    
    # Interpretation
    directionality: Directionality = Directionality.HIGHER_BETTER
    
    # Transforms to generate
    transforms: list[TransformType] = field(default_factory=lambda: [TransformType.RAW])
    
    # Data requirements
    requires: list[DataRequirement] = field(default_factory=lambda: [DataRequirement.OHLCV])
    depends_on_features: list[str] = field(default_factory=list)  # Other feature names
    
    # Scope
    universe_scope: str = "all"  # "all", "equity", "etf", "bond"
    
    # Control
    enabled: bool = True
    priority: int = 1  # 1=highest priority
    version: str = "1.0.0"
    
    def get_full_name(self, lookback: Optional[int] = None, transform: TransformType = TransformType.RAW) -> str:
        """Generate the full feature name with lookback and transform."""
        base = self.name
        if lookback is not None:
            base = f"{base}_{lookback}d"
        if transform != TransformType.RAW:
            base = f"{base}_{transform.value}"
        return base
    
    def generate_variants(self) -> list[tuple[str, int, TransformType]]:
        """Generate all name variants (lookback × transform combinations)."""
        variants = []
        lookbacks = self.lookback_variants if self.lookback_variants else [self.lookback_days]
        
        for lb in lookbacks:
            for transform in self.transforms:
                full_name = self.get_full_name(lb, transform)
                variants.append((full_name, lb, transform))
        
        return variants


# =============================================================================
# FEATURE CATALOG - The Single Source of Truth
# =============================================================================

FEATURE_CATALOG: dict[str, FeatureDefinition] = {}


def register_feature(feature: FeatureDefinition) -> FeatureDefinition:
    """Register a feature in the catalog."""
    FEATURE_CATALOG[feature.name] = feature
    return feature


# -----------------------------------------------------------------------------
# MOMENTUM FAMILY
# -----------------------------------------------------------------------------

register_feature(FeatureDefinition(
    name="mom_ts",
    family=FeatureFamily.MOMENTUM,
    description="Time-series momentum (cumulative return)",
    horizon_family=HorizonFamily.MULTI,
    lookback_days=21,
    min_history=252,
    lookback_variants=[21, 63, 126, 252],
    directionality=Directionality.HIGHER_BETTER,
    transforms=[TransformType.RAW, TransformType.RANK, TransformType.ZSCORE],
    requires=[DataRequirement.OHLCV],
    priority=1,
))

register_feature(FeatureDefinition(
    name="mom_risk_adj",
    family=FeatureFamily.MOMENTUM,
    description="Risk-adjusted momentum (return / realized vol)",
    horizon_family=HorizonFamily.MULTI,
    lookback_days=21,
    min_history=252,
    lookback_variants=[21, 63, 126],
    directionality=Directionality.HIGHER_BETTER,
    transforms=[TransformType.RAW, TransformType.RANK, TransformType.ZSCORE],
    requires=[DataRequirement.OHLCV],
    priority=1,
))

register_feature(FeatureDefinition(
    name="mom_intermediate",
    family=FeatureFamily.MOMENTUM,
    description="Intermediate momentum ratio (63d / 21d)",
    horizon_family=HorizonFamily.MEDIUM,
    lookback_days=63,
    min_history=126,
    directionality=Directionality.HIGHER_BETTER,
    transforms=[TransformType.RAW, TransformType.RANK],
    requires=[DataRequirement.OHLCV],
    priority=2,
))

register_feature(FeatureDefinition(
    name="mom_residual",
    family=FeatureFamily.MOMENTUM,
    description="Residual momentum (after stripping factor betas)",
    horizon_family=HorizonFamily.MULTI,
    lookback_days=63,
    min_history=252,
    lookback_variants=[63, 126],
    directionality=Directionality.HIGHER_BETTER,
    transforms=[TransformType.RAW, TransformType.RANK, TransformType.ZSCORE],
    requires=[DataRequirement.OHLCV, DataRequirement.FACTOR_ETFS],
    priority=2,
))

# -----------------------------------------------------------------------------
# TREND QUALITY FAMILY
# -----------------------------------------------------------------------------

register_feature(FeatureDefinition(
    name="trend_slope",
    family=FeatureFamily.TREND,
    description="MA slope of log-price",
    horizon_family=HorizonFamily.MULTI,
    lookback_days=21,
    min_history=252,
    lookback_variants=[21, 63, 126],
    directionality=Directionality.HIGHER_BETTER,
    transforms=[TransformType.RAW, TransformType.RANK, TransformType.ZSCORE],
    requires=[DataRequirement.OHLCV],
    priority=1,
))

register_feature(FeatureDefinition(
    name="trend_adx",
    family=FeatureFamily.TREND,
    description="Average Directional Index (trend strength)",
    horizon_family=HorizonFamily.MULTI,
    lookback_days=14,
    min_history=63,
    lookback_variants=[14, 21],
    directionality=Directionality.HIGHER_BETTER,  # Higher = stronger trend
    transforms=[TransformType.RAW, TransformType.RANK],
    requires=[DataRequirement.OHLCV],
    priority=1,
))

register_feature(FeatureDefinition(
    name="trend_efficiency",
    family=FeatureFamily.TREND,
    description="Trend efficiency ratio (net move / total path)",
    horizon_family=HorizonFamily.MULTI,
    lookback_days=21,
    min_history=126,
    lookback_variants=[21, 63],
    directionality=Directionality.HIGHER_BETTER,
    transforms=[TransformType.RAW, TransformType.RANK],
    requires=[DataRequirement.OHLCV],
    priority=2,
))

register_feature(FeatureDefinition(
    name="trend_choppiness",
    family=FeatureFamily.TREND,
    description="Choppiness index (lower = more trending)",
    horizon_family=HorizonFamily.MULTI,
    lookback_days=14,
    min_history=63,
    lookback_variants=[14, 21],
    directionality=Directionality.LOWER_BETTER,  # Lower = less choppy = trending
    transforms=[TransformType.RAW, TransformType.RANK],
    requires=[DataRequirement.OHLCV],
    priority=2,
))

# -----------------------------------------------------------------------------
# BREAKOUT FAMILY
# -----------------------------------------------------------------------------

register_feature(FeatureDefinition(
    name="breakout_high",
    family=FeatureFamily.BREAKOUT,
    description="At N-day high (binary)",
    horizon_family=HorizonFamily.MULTI,
    lookback_days=20,
    min_history=252,
    lookback_variants=[20, 55, 252],
    directionality=Directionality.HIGHER_BETTER,
    transforms=[TransformType.RAW],  # Binary, no transforms
    requires=[DataRequirement.OHLCV],
    priority=1,
))

register_feature(FeatureDefinition(
    name="breakout_dist_high",
    family=FeatureFamily.BREAKOUT,
    description="Distance from N-day high (%)",
    horizon_family=HorizonFamily.MULTI,
    lookback_days=20,
    min_history=252,
    lookback_variants=[20, 55, 252],
    directionality=Directionality.HIGHER_BETTER,  # Closer to high = better
    transforms=[TransformType.RAW, TransformType.RANK],
    requires=[DataRequirement.OHLCV],
    priority=1,
))

register_feature(FeatureDefinition(
    name="breakout_dist_low",
    family=FeatureFamily.BREAKOUT,
    description="Distance from N-day low (%)",
    horizon_family=HorizonFamily.MULTI,
    lookback_days=20,
    min_history=252,
    lookback_variants=[20, 55, 252],
    directionality=Directionality.HIGHER_BETTER,  # Further from low = better
    transforms=[TransformType.RAW, TransformType.RANK],
    requires=[DataRequirement.OHLCV],
    priority=2,
))

# -----------------------------------------------------------------------------
# MEAN REVERSION FAMILY
# -----------------------------------------------------------------------------

register_feature(FeatureDefinition(
    name="mr_zscore",
    family=FeatureFamily.MEAN_REVERSION,
    description="Distance from mean z-score: (price - SMA) / rolling_std",
    horizon_family=HorizonFamily.MULTI,
    lookback_days=20,
    min_history=126,
    lookback_variants=[20, 60],
    directionality=Directionality.LOWER_BETTER,  # More oversold = buy signal
    transforms=[TransformType.RAW, TransformType.RANK],
    requires=[DataRequirement.OHLCV],
    priority=1,
))

register_feature(FeatureDefinition(
    name="mr_reversal",
    family=FeatureFamily.MEAN_REVERSION,
    description="Short-term return reversal",
    horizon_family=HorizonFamily.FAST,
    lookback_days=5,
    min_history=63,
    lookback_variants=[3, 5, 10],
    directionality=Directionality.LOWER_BETTER,  # Recent losers = buy
    transforms=[TransformType.RAW, TransformType.RANK, TransformType.ZSCORE],
    requires=[DataRequirement.OHLCV],
    priority=1,
))

register_feature(FeatureDefinition(
    name="mr_dip_in_uptrend",
    family=FeatureFamily.MEAN_REVERSION,
    description="Pullback in uptrend: price > 200d MA AND zscore(20) < 0",
    horizon_family=HorizonFamily.MEDIUM,
    lookback_days=200,
    min_history=252,
    directionality=Directionality.HIGHER_BETTER,
    transforms=[TransformType.RAW],  # Binary signal
    requires=[DataRequirement.OHLCV],
    depends_on_features=["mr_zscore"],
    priority=1,
))

register_feature(FeatureDefinition(
    name="mr_rsi",
    family=FeatureFamily.MEAN_REVERSION,
    description="RSI (oversold/overbought indicator)",
    horizon_family=HorizonFamily.FAST,
    lookback_days=14,
    min_history=63,
    lookback_variants=[14],
    directionality=Directionality.NEUTRAL,  # Both extremes are signals
    transforms=[TransformType.RAW, TransformType.RANK],
    requires=[DataRequirement.OHLCV],
    priority=1,
))

# -----------------------------------------------------------------------------
# FACTOR PROXY FAMILY
# -----------------------------------------------------------------------------

register_feature(FeatureDefinition(
    name="factor_beta_mom",
    family=FeatureFamily.FACTOR,
    description="Rolling beta to MTUM (momentum factor)",
    horizon_family=HorizonFamily.MULTI,
    lookback_days=63,
    min_history=252,
    lookback_variants=[63, 126],
    parameters={"factor_etf": "MTUM"},
    directionality=Directionality.NEUTRAL,
    transforms=[TransformType.RAW, TransformType.RANK],
    requires=[DataRequirement.OHLCV, DataRequirement.FACTOR_ETFS],
    priority=2,
))

register_feature(FeatureDefinition(
    name="factor_beta_qual",
    family=FeatureFamily.FACTOR,
    description="Rolling beta to QUAL (quality factor)",
    horizon_family=HorizonFamily.MULTI,
    lookback_days=63,
    min_history=252,
    lookback_variants=[63, 126],
    parameters={"factor_etf": "QUAL"},
    directionality=Directionality.NEUTRAL,
    transforms=[TransformType.RAW, TransformType.RANK],
    requires=[DataRequirement.OHLCV, DataRequirement.FACTOR_ETFS],
    priority=2,
))

register_feature(FeatureDefinition(
    name="factor_beta_lowvol",
    family=FeatureFamily.FACTOR,
    description="Rolling beta to USMV (low volatility factor)",
    horizon_family=HorizonFamily.MULTI,
    lookback_days=63,
    min_history=252,
    lookback_variants=[63, 126],
    parameters={"factor_etf": "USMV"},
    directionality=Directionality.NEUTRAL,
    transforms=[TransformType.RAW, TransformType.RANK],
    requires=[DataRequirement.OHLCV, DataRequirement.FACTOR_ETFS],
    priority=2,
))

register_feature(FeatureDefinition(
    name="factor_beta_value",
    family=FeatureFamily.FACTOR,
    description="Rolling beta to VLUE (value factor)",
    horizon_family=HorizonFamily.MULTI,
    lookback_days=63,
    min_history=252,
    lookback_variants=[63, 126],
    parameters={"factor_etf": "VLUE"},
    directionality=Directionality.NEUTRAL,
    transforms=[TransformType.RAW, TransformType.RANK],
    requires=[DataRequirement.OHLCV, DataRequirement.FACTOR_ETFS],
    priority=2,
))

register_feature(FeatureDefinition(
    name="factor_beta_size",
    family=FeatureFamily.FACTOR,
    description="Rolling beta to SIZE/IWM (size factor)",
    horizon_family=HorizonFamily.MULTI,
    lookback_days=63,
    min_history=252,
    lookback_variants=[63, 126],
    parameters={"factor_etf": "IWM"},
    directionality=Directionality.NEUTRAL,
    transforms=[TransformType.RAW, TransformType.RANK],
    requires=[DataRequirement.OHLCV, DataRequirement.FACTOR_ETFS],
    priority=2,
))

register_feature(FeatureDefinition(
    name="factor_beta_spy",
    family=FeatureFamily.FACTOR,
    description="Rolling beta to SPY (market beta)",
    horizon_family=HorizonFamily.MULTI,
    lookback_days=63,
    min_history=252,
    lookback_variants=[63, 126],
    parameters={"factor_etf": "SPY"},
    directionality=Directionality.NEUTRAL,
    transforms=[TransformType.RAW, TransformType.RANK],
    requires=[DataRequirement.OHLCV, DataRequirement.BENCHMARK],
    priority=1,
))

register_feature(FeatureDefinition(
    name="factor_tilt_score",
    family=FeatureFamily.FACTOR,
    description="Composite factor tilt: quality + lowvol - value exposure",
    horizon_family=HorizonFamily.SLOW,
    lookback_days=126,
    min_history=252,
    directionality=Directionality.HIGHER_BETTER,
    transforms=[TransformType.RAW, TransformType.RANK],
    requires=[DataRequirement.OHLCV, DataRequirement.FACTOR_ETFS],
    depends_on_features=["factor_beta_qual", "factor_beta_lowvol", "factor_beta_value"],
    priority=3,
))

# -----------------------------------------------------------------------------
# RISK/STABILITY FAMILY
# -----------------------------------------------------------------------------

register_feature(FeatureDefinition(
    name="risk_realized_vol",
    family=FeatureFamily.RISK,
    description="Realized volatility (annualized)",
    horizon_family=HorizonFamily.MULTI,
    lookback_days=21,
    min_history=126,
    lookback_variants=[21, 63],
    directionality=Directionality.LOWER_BETTER,
    transforms=[TransformType.RAW, TransformType.RANK],
    requires=[DataRequirement.OHLCV],
    priority=1,
))

register_feature(FeatureDefinition(
    name="risk_idio_vol",
    family=FeatureFamily.RISK,
    description="Idiosyncratic volatility (residual vol vs SPY)",
    horizon_family=HorizonFamily.MEDIUM,
    lookback_days=63,
    min_history=252,
    directionality=Directionality.LOWER_BETTER,
    transforms=[TransformType.RAW, TransformType.RANK],
    requires=[DataRequirement.OHLCV, DataRequirement.BENCHMARK],
    priority=2,
))

register_feature(FeatureDefinition(
    name="risk_beta_trend",
    family=FeatureFamily.RISK,
    description="Beta trend (21d change in 63d beta)",
    horizon_family=HorizonFamily.MEDIUM,
    lookback_days=84,
    min_history=252,
    directionality=Directionality.NEUTRAL,
    transforms=[TransformType.RAW, TransformType.RANK],
    requires=[DataRequirement.OHLCV, DataRequirement.BENCHMARK],
    depends_on_features=["factor_beta_spy"],
    priority=3,
))

register_feature(FeatureDefinition(
    name="risk_drawdown",
    family=FeatureFamily.RISK,
    description="Maximum drawdown over N days",
    horizon_family=HorizonFamily.MEDIUM,
    lookback_days=63,
    min_history=126,
    directionality=Directionality.LOWER_BETTER,  # Smaller drawdown = better
    transforms=[TransformType.RAW, TransformType.RANK],
    requires=[DataRequirement.OHLCV],
    priority=1,
))

register_feature(FeatureDefinition(
    name="risk_downside_vol",
    family=FeatureFamily.RISK,
    description="Downside semi-variance (volatility of negative returns only)",
    horizon_family=HorizonFamily.MEDIUM,
    lookback_days=63,
    min_history=126,
    directionality=Directionality.LOWER_BETTER,
    transforms=[TransformType.RAW, TransformType.RANK],
    requires=[DataRequirement.OHLCV],
    priority=2,
))

# -----------------------------------------------------------------------------
# UDR/CAPTURE FAMILY
# -----------------------------------------------------------------------------

register_feature(FeatureDefinition(
    name="udr_up_capture",
    family=FeatureFamily.UDR,
    description="Up capture ratio vs benchmark",
    horizon_family=HorizonFamily.MULTI,
    lookback_days=63,
    min_history=252,
    lookback_variants=[63, 126],
    directionality=Directionality.HIGHER_BETTER,
    transforms=[TransformType.RAW, TransformType.RANK],
    requires=[DataRequirement.OHLCV, DataRequirement.BENCHMARK],
    priority=1,
))

register_feature(FeatureDefinition(
    name="udr_down_capture",
    family=FeatureFamily.UDR,
    description="Down capture ratio vs benchmark",
    horizon_family=HorizonFamily.MULTI,
    lookback_days=63,
    min_history=252,
    lookback_variants=[63, 126],
    directionality=Directionality.LOWER_BETTER,  # Lower down capture = better protection
    transforms=[TransformType.RAW, TransformType.RANK],
    requires=[DataRequirement.OHLCV, DataRequirement.BENCHMARK],
    priority=1,
))

register_feature(FeatureDefinition(
    name="udr_capture_asymmetry",
    family=FeatureFamily.UDR,
    description="Capture asymmetry (up capture / down capture)",
    horizon_family=HorizonFamily.MULTI,
    lookback_days=63,
    min_history=252,
    lookback_variants=[63, 126],
    directionality=Directionality.HIGHER_BETTER,
    transforms=[TransformType.RAW, TransformType.RANK],
    requires=[DataRequirement.OHLCV, DataRequirement.BENCHMARK],
    depends_on_features=["udr_up_capture", "udr_down_capture"],
    priority=2,
))

register_feature(FeatureDefinition(
    name="udr_capture_delta",
    family=FeatureFamily.UDR,
    description="Capture improvement (recent vs prior period)",
    horizon_family=HorizonFamily.MEDIUM,
    lookback_days=126,
    min_history=252,
    directionality=Directionality.HIGHER_BETTER,
    transforms=[TransformType.RAW, TransformType.RANK],
    requires=[DataRequirement.OHLCV, DataRequirement.BENCHMARK],
    depends_on_features=["udr_capture_asymmetry"],
    priority=3,
))

# -----------------------------------------------------------------------------
# REGIME INDICATORS
# -----------------------------------------------------------------------------

register_feature(FeatureDefinition(
    name="regime_hurst",
    family=FeatureFamily.REGIME,
    description="Hurst exponent (>0.5 = trending, <0.5 = mean-reverting)",
    horizon_family=HorizonFamily.SLOW,
    lookback_days=126,
    min_history=252,
    directionality=Directionality.NEUTRAL,
    transforms=[TransformType.RAW],
    requires=[DataRequirement.OHLCV],
    priority=1,
))

register_feature(FeatureDefinition(
    name="regime_variance_ratio",
    family=FeatureFamily.REGIME,
    description="Variance ratio test for random walk",
    horizon_family=HorizonFamily.SLOW,
    lookback_days=126,
    min_history=252,
    directionality=Directionality.NEUTRAL,
    transforms=[TransformType.RAW],
    requires=[DataRequirement.OHLCV],
    priority=2,
))

register_feature(FeatureDefinition(
    name="regime_vol_level",
    family=FeatureFamily.REGIME,
    description="Volatility regime level (percentile of historical vol)",
    horizon_family=HorizonFamily.MEDIUM,
    lookback_days=21,
    min_history=252,
    directionality=Directionality.NEUTRAL,
    transforms=[TransformType.RAW],
    requires=[DataRequirement.OHLCV],
    depends_on_features=["risk_realized_vol"],
    priority=1,
))

register_feature(FeatureDefinition(
    name="regime_corr_dispersion",
    family=FeatureFamily.REGIME,
    description="Cross-sectional return dispersion",
    horizon_family=HorizonFamily.FAST,
    lookback_days=21,
    min_history=126,
    directionality=Directionality.NEUTRAL,
    transforms=[TransformType.RAW],
    requires=[DataRequirement.OHLCV],
    universe_scope="all",  # Computed across universe
    priority=1,
))

register_feature(FeatureDefinition(
    name="regime_corr_spy",
    family=FeatureFamily.REGIME,
    description="Rolling correlation to SPY",
    horizon_family=HorizonFamily.MEDIUM,
    lookback_days=63,
    min_history=126,
    directionality=Directionality.NEUTRAL,
    transforms=[TransformType.RAW, TransformType.RANK],
    requires=[DataRequirement.OHLCV, DataRequirement.BENCHMARK],
    priority=1,
))


# =============================================================================
# SCHEMA UTILITIES
# =============================================================================

def get_all_features() -> list[FeatureDefinition]:
    """Get all registered features."""
    return list(FEATURE_CATALOG.values())


def get_enabled_features() -> list[FeatureDefinition]:
    """Get all enabled features."""
    return [f for f in FEATURE_CATALOG.values() if f.enabled]


def get_features_by_family(family: FeatureFamily) -> list[FeatureDefinition]:
    """Get features by family."""
    return [f for f in FEATURE_CATALOG.values() if f.family == family]


def get_features_by_priority(max_priority: int = 2) -> list[FeatureDefinition]:
    """Get features up to a priority level (1 = highest)."""
    return [f for f in FEATURE_CATALOG.values() if f.priority <= max_priority and f.enabled]


def get_feature(name: str) -> Optional[FeatureDefinition]:
    """Get a feature by name."""
    return FEATURE_CATALOG.get(name)


def get_all_feature_variants() -> list[tuple[str, FeatureDefinition, int, TransformType]]:
    """
    Get all feature name variants with their definitions.
    
    Returns list of (full_name, definition, lookback, transform)
    """
    variants = []
    for feature in get_enabled_features():
        for full_name, lookback, transform in feature.generate_variants():
            variants.append((full_name, feature, lookback, transform))
    return variants


def count_total_features() -> dict[str, int]:
    """Count total features by family."""
    counts = {}
    for feature in get_enabled_features():
        family = feature.family.value
        variant_count = len(feature.generate_variants())
        counts[family] = counts.get(family, 0) + variant_count
    counts["total"] = sum(counts.values())
    return counts


# Configuration for benchmarks and factor ETFs
BENCHMARK_CONFIG = {
    "primary": "SPY",
    "secondary": ["AGG"],  # For future use
}

FACTOR_ETF_CONFIG = {
    "momentum": "MTUM",
    "quality": "QUAL",
    "low_volatility": "USMV",
    "value": "VLUE",
    "size": "IWM",
    # Sector ETFs for sector-neutral residuals
    "sector_tech": "XLK",
    "sector_healthcare": "XLV",
    "sector_financials": "XLF",
    "sector_energy": "XLE",
    "sector_materials": "XLB",
    "sector_industrials": "XLI",
    "sector_staples": "XLP",
    "sector_discretionary": "XLY",
    "sector_utilities": "XLU",
    "sector_realestate": "XLRE",
    "sector_communication": "XLC",
}

# Forward return horizons for IC calculation
IC_HORIZONS = [5, 21, 63, 126]
