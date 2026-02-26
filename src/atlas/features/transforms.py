"""
Panel Transformation Layer - Cross-sectional transforms.

Applies transforms like rank, zscore, quintile across the universe
for a given date. These transforms turn raw time-series features
into cross-sectional signals.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats

from atlas.core.logging import get_logger
from atlas.features.schema import TransformType

logger = get_logger(__name__)


@dataclass
class TransformResult:
    """Result of a panel transformation."""
    
    feature_name: str
    transform_type: TransformType
    trade_date: date
    values: pd.Series  # Indexed by instrument_id
    
    # Statistics
    n_instruments: int = 0
    n_valid: int = 0
    raw_mean: float = 0.0
    raw_std: float = 0.0


class PanelTransformer:
    """
    Applies cross-sectional transformations to feature values.
    
    For each date, transforms raw feature values across all instruments
    into ranks, z-scores, or bucket assignments.
    """
    
    def __init__(
        self,
        winsorize_pct: float = 0.025,  # 2.5% tails
        zscore_clip: float = 3.0,      # Clip z-scores at ±3
    ):
        self.winsorize_pct = winsorize_pct
        self.zscore_clip = zscore_clip
    
    def transform(
        self,
        raw_values: pd.Series,
        transform_type: TransformType,
        feature_name: str,
        trade_date: date,
    ) -> TransformResult:
        """
        Apply a transformation to raw feature values.
        
        Args:
            raw_values: Series indexed by instrument_id
            transform_type: Type of transform to apply
            feature_name: Base feature name
            trade_date: Date of the values
            
        Returns:
            TransformResult with transformed values
        """
        # Filter out NaN for transformation
        valid_values = raw_values.dropna()
        
        result = TransformResult(
            feature_name=f"{feature_name}_{transform_type.value}" if transform_type != TransformType.RAW else feature_name,
            transform_type=transform_type,
            trade_date=trade_date,
            values=pd.Series(dtype=float),
            n_instruments=len(raw_values),
            n_valid=len(valid_values),
        )
        
        if len(valid_values) < 2:
            result.values = raw_values.copy()
            return result
        
        result.raw_mean = valid_values.mean()
        result.raw_std = valid_values.std()
        
        if transform_type == TransformType.RAW:
            result.values = raw_values.copy()
            
        elif transform_type == TransformType.RANK:
            result.values = self._rank_transform(raw_values, valid_values)
            
        elif transform_type == TransformType.ZSCORE:
            result.values = self._zscore_transform(raw_values, valid_values)
            
        elif transform_type == TransformType.QUINTILE:
            result.values = self._bucket_transform(raw_values, valid_values, n_buckets=5)
            
        elif transform_type == TransformType.DECILE:
            result.values = self._bucket_transform(raw_values, valid_values, n_buckets=10)
        
        return result
    
    def _rank_transform(
        self,
        raw_values: pd.Series,
        valid_values: pd.Series,
    ) -> pd.Series:
        """
        Transform to percentile rank (0-100).
        
        Higher rank = higher raw value.
        """
        # Rank valid values
        ranks = valid_values.rank(pct=True) * 100
        
        # Map back to full series (NaN stays NaN)
        result = pd.Series(index=raw_values.index, dtype=float)
        result[ranks.index] = ranks
        
        return result
    
    def _zscore_transform(
        self,
        raw_values: pd.Series,
        valid_values: pd.Series,
    ) -> pd.Series:
        """
        Transform to cross-sectional z-score.
        
        1. Winsorize tails
        2. Standardize (mean=0, std=1)
        3. Clip to ±zscore_clip
        """
        # Winsorize
        lower = valid_values.quantile(self.winsorize_pct)
        upper = valid_values.quantile(1 - self.winsorize_pct)
        winsorized = valid_values.clip(lower, upper)
        
        # Standardize
        mean = winsorized.mean()
        std = winsorized.std()
        
        if std == 0 or np.isnan(std):
            # All values are the same
            zscores = pd.Series(0.0, index=valid_values.index)
        else:
            zscores = (winsorized - mean) / std
            # Clip
            zscores = zscores.clip(-self.zscore_clip, self.zscore_clip)
        
        # Map back to full series
        result = pd.Series(index=raw_values.index, dtype=float)
        result[zscores.index] = zscores
        
        return result
    
    def _bucket_transform(
        self,
        raw_values: pd.Series,
        valid_values: pd.Series,
        n_buckets: int,
    ) -> pd.Series:
        """
        Transform to bucket assignment (1 to n_buckets).
        
        1 = lowest bucket, n_buckets = highest bucket.
        """
        # Use qcut for equal-sized buckets
        try:
            buckets = pd.qcut(valid_values, n_buckets, labels=False, duplicates="drop") + 1
        except ValueError:
            # Too few unique values for n_buckets
            buckets = pd.Series(n_buckets // 2, index=valid_values.index)
        
        # Map back to full series
        result = pd.Series(index=raw_values.index, dtype=float)
        result[buckets.index] = buckets
        
        return result
    
    def transform_batch(
        self,
        raw_features: pd.DataFrame,
        transform_types: dict[str, list[TransformType]],
        trade_date: date,
    ) -> pd.DataFrame:
        """
        Transform multiple features at once.
        
        Args:
            raw_features: DataFrame with columns = feature names, index = instrument_id
            transform_types: Dict mapping feature name -> list of transforms
            trade_date: Date of the values
            
        Returns:
            DataFrame with all transformed features
        """
        results = {}
        
        for feature_name in raw_features.columns:
            raw_values = raw_features[feature_name]
            transforms = transform_types.get(feature_name, [TransformType.RAW])
            
            for transform in transforms:
                result = self.transform(raw_values, transform, feature_name, trade_date)
                results[result.feature_name] = result.values
        
        return pd.DataFrame(results)


class CrossSectionalStats:
    """Calculate cross-sectional statistics for a panel of features."""
    
    @staticmethod
    def dispersion(returns: pd.DataFrame) -> float:
        """
        Calculate cross-sectional dispersion.
        
        Args:
            returns: DataFrame of returns (columns = instruments)
            
        Returns:
            Standard deviation of returns across instruments
        """
        return returns.std(axis=1).mean()
    
    @staticmethod
    def average_correlation(returns: pd.DataFrame, benchmark: Optional[pd.Series] = None) -> float:
        """
        Calculate average pairwise correlation or average correlation to benchmark.
        
        Args:
            returns: DataFrame of returns
            benchmark: Optional benchmark returns
            
        Returns:
            Average correlation
        """
        if benchmark is not None:
            # Correlation to benchmark
            corrs = returns.corrwith(benchmark)
            return corrs.mean()
        else:
            # Pairwise correlation (can be slow for many instruments)
            corr_matrix = returns.corr()
            n = len(corr_matrix)
            if n < 2:
                return np.nan
            # Average of upper triangle (excluding diagonal)
            upper = np.triu(corr_matrix.values, k=1)
            return upper[upper != 0].mean()
    
    @staticmethod
    def compute_regime_indicators(
        returns: pd.DataFrame,
        benchmark_returns: pd.Series,
        lookback: int = 21,
    ) -> dict[str, float]:
        """
        Compute regime indicators from a panel of returns.
        
        Args:
            returns: DataFrame of returns (columns = instruments)
            benchmark_returns: Benchmark returns
            lookback: Lookback period
            
        Returns:
            Dict of regime indicator values
        """
        regime = {}
        
        # Dispersion
        regime["dispersion"] = returns.iloc[-lookback:].std(axis=1).mean()
        
        # Average correlation to benchmark
        recent_returns = returns.iloc[-lookback:]
        recent_bench = benchmark_returns.iloc[-lookback:]
        corrs = recent_returns.corrwith(recent_bench)
        regime["avg_corr_spy"] = corrs.mean()
        
        # Benchmark volatility
        regime["benchmark_vol"] = recent_bench.std() * np.sqrt(252)
        
        # Benchmark trend (simple)
        if len(recent_bench) >= lookback:
            regime["benchmark_trend"] = recent_bench.sum()  # Cumulative return
        
        return regime
