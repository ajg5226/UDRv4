"""
Feature Diagnostics - IC, hit rate, and stability metrics.

Computes and stores signal quality diagnostics for each feature,
enabling evidence-based composite construction and signal exclusion.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats

from atlas.core.logging import get_logger
from atlas.features.schema import IC_HORIZONS

logger = get_logger(__name__)


@dataclass
class FeatureDiagnostic:
    """Diagnostic results for a single feature."""
    
    feature_name: str
    feature_version: str
    calc_date: date
    forward_horizon: int  # Days
    universe_scope: str
    
    # Core metrics
    ic_spearman: float = np.nan      # Rank correlation with forward returns
    ic_pearson: float = np.nan       # Linear correlation
    hit_rate: float = np.nan         # % correct sign predictions
    t_stat: float = np.nan           # Statistical significance
    n_observations: int = 0
    
    # Regime conditioning
    regime: str = "all"              # "all", "trending", "mean_reverting", "high_vol", "low_vol"
    
    # Stability metrics
    ic_std: float = np.nan           # Rolling IC standard deviation
    ic_mean: float = np.nan          # Rolling IC mean
    ic_ir: float = np.nan            # IC Information Ratio (mean/std)
    
    @property
    def is_significant(self) -> bool:
        """Check if IC is statistically significant at 5% level."""
        return abs(self.t_stat) > 1.96 if not np.isnan(self.t_stat) else False
    
    @property
    def is_stable(self) -> bool:
        """Check if IC is reasonably stable (IR > 0.5)."""
        return self.ic_ir > 0.5 if not np.isnan(self.ic_ir) else False


class DiagnosticsCalculator:
    """
    Calculates feature diagnostics.
    
    Computes IC, hit rate, and other quality metrics for features
    against forward returns at multiple horizons.
    """
    
    def __init__(
        self,
        horizons: list[int] = None,
        min_observations: int = 30,
        rolling_window: int = 252,  # For stability metrics
    ):
        self.horizons = horizons or IC_HORIZONS
        self.min_observations = min_observations
        self.rolling_window = rolling_window
    
    def calculate_ic(
        self,
        feature_values: pd.Series,
        forward_returns: pd.Series,
    ) -> tuple[float, float, float, int]:
        """
        Calculate Information Coefficient (IC) and related metrics.
        
        Args:
            feature_values: Feature values indexed by instrument_id
            forward_returns: Forward returns indexed by instrument_id
            
        Returns:
            (ic_spearman, ic_pearson, t_stat, n_observations)
        """
        # Align data
        aligned = pd.concat([feature_values, forward_returns], axis=1, join="inner")
        aligned.columns = ["feature", "return"]
        aligned = aligned.dropna()
        
        n = len(aligned)
        if n < self.min_observations:
            return np.nan, np.nan, np.nan, n
        
        # Spearman (rank) correlation
        ic_spearman, _ = stats.spearmanr(aligned["feature"], aligned["return"])
        
        # Pearson (linear) correlation
        ic_pearson, _ = stats.pearsonr(aligned["feature"], aligned["return"])
        
        # T-statistic for Spearman IC
        t_stat = ic_spearman * np.sqrt((n - 2) / (1 - ic_spearman**2)) if abs(ic_spearman) < 1 else np.nan
        
        return ic_spearman, ic_pearson, t_stat, n
    
    def calculate_hit_rate(
        self,
        feature_values: pd.Series,
        forward_returns: pd.Series,
        directionality: str = "higher_better",
    ) -> float:
        """
        Calculate hit rate (sign correctness).
        
        Args:
            feature_values: Feature values
            forward_returns: Forward returns
            directionality: "higher_better" or "lower_better"
            
        Returns:
            Hit rate (0-1)
        """
        aligned = pd.concat([feature_values, forward_returns], axis=1, join="inner")
        aligned.columns = ["feature", "return"]
        aligned = aligned.dropna()
        
        if len(aligned) < self.min_observations:
            return np.nan
        
        # Determine expected relationship
        if directionality == "higher_better":
            # High feature -> positive return
            # Use median split
            median_feature = aligned["feature"].median()
            high_feature = aligned["feature"] > median_feature
            positive_return = aligned["return"] > 0
            
            # Hit = (high feature AND positive return) OR (low feature AND negative return)
            hits = (high_feature & positive_return) | (~high_feature & ~positive_return)
        else:
            # Low feature -> positive return
            median_feature = aligned["feature"].median()
            low_feature = aligned["feature"] < median_feature
            positive_return = aligned["return"] > 0
            
            hits = (low_feature & positive_return) | (~low_feature & ~positive_return)
        
        return hits.mean()
    
    def calculate_diagnostics(
        self,
        feature_name: str,
        feature_version: str,
        feature_values: pd.DataFrame,  # Index: date, Columns: instrument_id
        price_data: pd.DataFrame,       # For computing forward returns
        calc_date: date,
        universe_scope: str = "all",
        directionality: str = "higher_better",
        regime: str = "all",
    ) -> list[FeatureDiagnostic]:
        """
        Calculate diagnostics for a feature across all horizons.
        
        Args:
            feature_name: Name of the feature
            feature_version: Version string
            feature_values: Panel of feature values (dates × instruments)
            price_data: OHLCV data for computing forward returns
            calc_date: Date to calculate diagnostics for
            universe_scope: Scope identifier
            directionality: Feature directionality
            regime: Regime label
            
        Returns:
            List of FeatureDiagnostic, one per horizon
        """
        results = []
        
        # Get feature values for calc_date
        if calc_date not in feature_values.index:
            logger.warning(f"No feature values for {calc_date}")
            return results
        
        feature_on_date = feature_values.loc[calc_date]
        
        for horizon in self.horizons:
            # Compute forward returns
            forward_date = calc_date + timedelta(days=horizon)
            forward_returns = self._compute_forward_returns(
                price_data, calc_date, horizon
            )
            
            if forward_returns is None or forward_returns.empty:
                continue
            
            # Calculate IC
            ic_spearman, ic_pearson, t_stat, n = self.calculate_ic(
                feature_on_date, forward_returns
            )
            
            # Calculate hit rate
            hit_rate = self.calculate_hit_rate(
                feature_on_date, forward_returns, directionality
            )
            
            diagnostic = FeatureDiagnostic(
                feature_name=feature_name,
                feature_version=feature_version,
                calc_date=calc_date,
                forward_horizon=horizon,
                universe_scope=universe_scope,
                ic_spearman=ic_spearman,
                ic_pearson=ic_pearson,
                hit_rate=hit_rate,
                t_stat=t_stat,
                n_observations=n,
                regime=regime,
            )
            
            results.append(diagnostic)
        
        return results
    
    def _compute_forward_returns(
        self,
        price_data: pd.DataFrame,
        start_date: date,
        horizon: int,
    ) -> Optional[pd.Series]:
        """Compute forward returns from start_date over horizon days."""
        # Get prices on start_date and start_date + horizon
        start_prices = price_data[price_data["trade_date"] == start_date]
        
        end_date = start_date + timedelta(days=horizon)
        # Find the actual trading day closest to end_date
        future_data = price_data[price_data["trade_date"] > start_date]
        if future_data.empty:
            return None
        
        # Get prices around the horizon date
        end_prices = future_data[
            future_data["trade_date"] <= end_date + timedelta(days=5)
        ].groupby("instrument_id").last()
        
        if start_prices.empty or end_prices.empty:
            return None
        
        # Compute returns
        start_prices = start_prices.set_index("instrument_id")["adj_close"]
        end_prices = end_prices["adj_close"]
        
        aligned = pd.concat([start_prices, end_prices], axis=1, join="inner")
        aligned.columns = ["start", "end"]
        
        returns = (aligned["end"] - aligned["start"]) / aligned["start"]
        
        return returns
    
    def calculate_rolling_ic_stats(
        self,
        feature_name: str,
        historical_ics: pd.Series,  # Series of IC values over time
    ) -> dict[str, float]:
        """
        Calculate rolling IC statistics for stability assessment.
        
        Args:
            feature_name: Feature name
            historical_ics: Series of historical IC values (index: date)
            
        Returns:
            Dict with ic_mean, ic_std, ic_ir
        """
        if len(historical_ics) < 12:  # Need at least 12 observations
            return {"ic_mean": np.nan, "ic_std": np.nan, "ic_ir": np.nan}
        
        ic_mean = historical_ics.mean()
        ic_std = historical_ics.std()
        ic_ir = ic_mean / ic_std if ic_std > 0 else np.nan
        
        return {
            "ic_mean": ic_mean,
            "ic_std": ic_std,
            "ic_ir": ic_ir,
        }


class DiagnosticsStore:
    """
    Interface for storing and retrieving feature diagnostics.
    
    Integrates with the database to persist diagnostic results.
    """
    
    def __init__(self, db_session):
        self.session = db_session
    
    def save_diagnostics(self, diagnostics: list[FeatureDiagnostic], run_id: int) -> int:
        """
        Save diagnostics to the database.
        
        Args:
            diagnostics: List of diagnostic results
            run_id: Pipeline run ID
            
        Returns:
            Number of records saved
        """
        from atlas.storage.models import FeatureDiagnosticRecord
        
        count = 0
        for diag in diagnostics:
            record = FeatureDiagnosticRecord(
                feature_name=diag.feature_name,
                feature_version=diag.feature_version,
                universe_scope=diag.universe_scope,
                calc_date=diag.calc_date,
                forward_horizon=diag.forward_horizon,
                ic_spearman=diag.ic_spearman if not np.isnan(diag.ic_spearman) else None,
                ic_pearson=diag.ic_pearson if not np.isnan(diag.ic_pearson) else None,
                hit_rate=diag.hit_rate if not np.isnan(diag.hit_rate) else None,
                t_stat=diag.t_stat if not np.isnan(diag.t_stat) else None,
                n_observations=diag.n_observations,
                regime=diag.regime,
                run_id=run_id,
            )
            self.session.add(record)
            count += 1
        
        self.session.flush()
        return count
    
    def get_historical_ic(
        self,
        feature_name: str,
        horizon: int,
        lookback_days: int = 252,
    ) -> pd.Series:
        """
        Get historical IC values for a feature.
        
        Args:
            feature_name: Feature name
            horizon: Forward horizon
            lookback_days: Days of history to retrieve
            
        Returns:
            Series of IC values indexed by date
        """
        from datetime import datetime, timedelta
        from sqlalchemy import select
        from atlas.storage.models import FeatureDiagnosticRecord
        
        start_date = datetime.now().date() - timedelta(days=lookback_days)
        
        stmt = select(FeatureDiagnosticRecord).where(
            FeatureDiagnosticRecord.feature_name == feature_name,
            FeatureDiagnosticRecord.forward_horizon == horizon,
            FeatureDiagnosticRecord.calc_date >= start_date,
        ).order_by(FeatureDiagnosticRecord.calc_date)
        
        results = list(self.session.scalars(stmt))
        
        if not results:
            return pd.Series(dtype=float)
        
        return pd.Series(
            {r.calc_date: r.ic_spearman for r in results if r.ic_spearman is not None}
        )
    
    def get_feature_quality_summary(
        self,
        feature_names: list[str] = None,
        horizon: int = 21,
        min_observations: int = 60,
    ) -> pd.DataFrame:
        """
        Get quality summary for features.
        
        Args:
            feature_names: List of features (None = all)
            horizon: Forward horizon to summarize
            min_observations: Minimum IC observations required
            
        Returns:
            DataFrame with feature quality metrics
        """
        from sqlalchemy import select, func
        from atlas.storage.models import FeatureDiagnosticRecord
        
        # Query aggregated stats
        stmt = select(
            FeatureDiagnosticRecord.feature_name,
            func.avg(FeatureDiagnosticRecord.ic_spearman).label("avg_ic"),
            func.stddev(FeatureDiagnosticRecord.ic_spearman).label("std_ic"),
            func.avg(FeatureDiagnosticRecord.hit_rate).label("avg_hit_rate"),
            func.count().label("n_obs"),
        ).where(
            FeatureDiagnosticRecord.forward_horizon == horizon,
        ).group_by(
            FeatureDiagnosticRecord.feature_name
        ).having(
            func.count() >= min_observations
        )
        
        if feature_names:
            stmt = stmt.where(FeatureDiagnosticRecord.feature_name.in_(feature_names))
        
        results = self.session.execute(stmt).fetchall()
        
        if not results:
            return pd.DataFrame()
        
        df = pd.DataFrame(results, columns=["feature_name", "avg_ic", "std_ic", "avg_hit_rate", "n_obs"])
        df["ic_ir"] = df["avg_ic"] / df["std_ic"]
        df = df.sort_values("ic_ir", ascending=False)
        
        return df
