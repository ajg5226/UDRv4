"""Base feature interface and data structures."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

import numpy as np
import pandas as pd


@dataclass
class FeatureResult:
    """Result of a feature calculation."""
    
    feature_name: str
    trade_date: date
    values: pd.Series  # Indexed by instrument_id
    
    # Metadata
    calculation_time_ms: float = 0.0
    instruments_calculated: int = 0
    instruments_failed: int = 0
    
    # Errors
    errors: list[str] = field(default_factory=list)
    
    @property
    def success(self) -> bool:
        """Check if calculation was successful."""
        return self.instruments_failed == 0 and len(self.errors) == 0


class BaseFeature(ABC):
    """
    Abstract base class for engineered features.
    
    All features must implement:
    - name: Unique feature identifier
    - dependencies: Required input data or other features
    - lookback_days: Historical data needed
    - calculate(): Compute feature values
    
    Features can optionally implement:
    - validate(): Validate calculated values
    - get_parameters(): Return configurable parameters
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique feature identifier (e.g., 'daily_return', 'sma_50')."""
        pass
    
    @property
    @abstractmethod
    def category(self) -> str:
        """Feature category (e.g., 'returns', 'volatility', 'momentum')."""
        pass
    
    @property
    @abstractmethod
    def dependencies(self) -> list[str]:
        """
        Required input data or other features.
        
        Examples:
        - ['adj_close'] for features that need adjusted close price
        - ['daily_return'] for features derived from returns
        - ['sma_50', 'sma_200'] for features comparing moving averages
        """
        pass
    
    @property
    @abstractmethod
    def lookback_days(self) -> int:
        """
        Number of historical days needed for calculation.
        
        Should be the maximum lookback needed. For example:
        - daily_return needs 2 days (current and previous)
        - sma_50 needs 50 days
        - volatility_21d needs 22 days (21 returns from 22 prices)
        """
        pass
    
    @property
    def description(self) -> str:
        """Human-readable description of the feature."""
        return f"{self.name} feature"
    
    @abstractmethod
    def calculate(
        self,
        data: pd.DataFrame,
        target_date: date,
        parameters: Optional[dict[str, Any]] = None,
    ) -> pd.Series:
        """
        Calculate feature values for a specific date.
        
        Args:
            data: Historical data with at least `lookback_days` of history.
                  Must include all columns specified in `dependencies`.
                  Expected to be indexed or have columns for instrument_id and trade_date.
            target_date: The date to calculate the feature for.
            parameters: Optional parameters to override defaults.
            
        Returns:
            Series indexed by instrument_id with calculated feature values.
            NaN values indicate calculation was not possible.
        """
        pass
    
    def validate(self, values: pd.Series) -> tuple[bool, list[str]]:
        """
        Validate calculated feature values.
        
        Args:
            values: Calculated feature values
            
        Returns:
            Tuple of (is_valid, list of error messages)
        """
        errors = []
        
        # Check for all NaN
        if values.isna().all():
            errors.append("All values are NaN")
        
        # Check for infinite values
        if np.isinf(values).any():
            inf_count = np.isinf(values).sum()
            errors.append(f"{inf_count} infinite values detected")
        
        return len(errors) == 0, errors
    
    def get_parameters(self) -> dict[str, Any]:
        """
        Get configurable parameters for this feature.
        
        Override in subclasses to expose parameters.
        
        Returns:
            Dict of parameter name -> default value
        """
        return {}
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name='{self.name}', category='{self.category}')>"


# ============================================
# COMMON FEATURE IMPLEMENTATIONS
# ============================================

class DailyReturn(BaseFeature):
    """Simple daily return."""
    
    @property
    def name(self) -> str:
        return "daily_return"
    
    @property
    def category(self) -> str:
        return "returns"
    
    @property
    def dependencies(self) -> list[str]:
        return ["adj_close"]
    
    @property
    def lookback_days(self) -> int:
        return 2
    
    def calculate(
        self,
        data: pd.DataFrame,
        target_date: date,
        parameters: Optional[dict[str, Any]] = None,
    ) -> pd.Series:
        # Calculate daily returns per instrument
        result = {}
        
        for instrument_id in data["instrument_id"].unique():
            inst_data = data[data["instrument_id"] == instrument_id].sort_values("trade_date")
            
            if len(inst_data) < 2:
                result[instrument_id] = np.nan
                continue
            
            # Get last two prices
            prices = inst_data["adj_close"].tail(2).values
            if prices[0] != 0 and not np.isnan(prices[0]):
                result[instrument_id] = (prices[1] - prices[0]) / prices[0]
            else:
                result[instrument_id] = np.nan
        
        return pd.Series(result, name=self.name)


class LogReturn(BaseFeature):
    """Logarithmic daily return."""
    
    @property
    def name(self) -> str:
        return "log_return"
    
    @property
    def category(self) -> str:
        return "returns"
    
    @property
    def dependencies(self) -> list[str]:
        return ["adj_close"]
    
    @property
    def lookback_days(self) -> int:
        return 2
    
    def calculate(
        self,
        data: pd.DataFrame,
        target_date: date,
        parameters: Optional[dict[str, Any]] = None,
    ) -> pd.Series:
        result = {}
        
        for instrument_id in data["instrument_id"].unique():
            inst_data = data[data["instrument_id"] == instrument_id].sort_values("trade_date")
            
            if len(inst_data) < 2:
                result[instrument_id] = np.nan
                continue
            
            prices = inst_data["adj_close"].tail(2).values
            if prices[0] > 0 and prices[1] > 0:
                result[instrument_id] = np.log(prices[1] / prices[0])
            else:
                result[instrument_id] = np.nan
        
        return pd.Series(result, name=self.name)


class CumulativeReturn(BaseFeature):
    """Cumulative return over a window."""
    
    def __init__(self, window: int = 21):
        self._window = window
    
    @property
    def name(self) -> str:
        return f"cumulative_return_{self._window}d"
    
    @property
    def category(self) -> str:
        return "returns"
    
    @property
    def dependencies(self) -> list[str]:
        return ["adj_close"]
    
    @property
    def lookback_days(self) -> int:
        return self._window + 1
    
    def get_parameters(self) -> dict[str, Any]:
        return {"window": self._window}
    
    def calculate(
        self,
        data: pd.DataFrame,
        target_date: date,
        parameters: Optional[dict[str, Any]] = None,
    ) -> pd.Series:
        window = parameters.get("window", self._window) if parameters else self._window
        result = {}
        
        for instrument_id in data["instrument_id"].unique():
            inst_data = data[data["instrument_id"] == instrument_id].sort_values("trade_date")
            
            if len(inst_data) < window + 1:
                result[instrument_id] = np.nan
                continue
            
            prices = inst_data["adj_close"].tail(window + 1).values
            if prices[0] != 0 and not np.isnan(prices[0]):
                result[instrument_id] = (prices[-1] - prices[0]) / prices[0]
            else:
                result[instrument_id] = np.nan
        
        return pd.Series(result, name=self.name)


class RealizedVolatility(BaseFeature):
    """Realized volatility over a window."""
    
    def __init__(self, window: int = 21, annualize: bool = True):
        self._window = window
        self._annualize = annualize
    
    @property
    def name(self) -> str:
        return f"realized_vol_{self._window}d"
    
    @property
    def category(self) -> str:
        return "volatility"
    
    @property
    def dependencies(self) -> list[str]:
        return ["adj_close"]
    
    @property
    def lookback_days(self) -> int:
        return self._window + 1
    
    def get_parameters(self) -> dict[str, Any]:
        return {"window": self._window, "annualize": self._annualize}
    
    def calculate(
        self,
        data: pd.DataFrame,
        target_date: date,
        parameters: Optional[dict[str, Any]] = None,
    ) -> pd.Series:
        window = parameters.get("window", self._window) if parameters else self._window
        annualize = parameters.get("annualize", self._annualize) if parameters else self._annualize
        result = {}
        
        for instrument_id in data["instrument_id"].unique():
            inst_data = data[data["instrument_id"] == instrument_id].sort_values("trade_date")
            
            if len(inst_data) < window + 1:
                result[instrument_id] = np.nan
                continue
            
            prices = inst_data["adj_close"].tail(window + 1).values
            
            # Calculate log returns
            log_returns = np.diff(np.log(prices))
            
            # Calculate standard deviation
            vol = np.std(log_returns, ddof=1)
            
            if annualize:
                vol *= np.sqrt(252)
            
            result[instrument_id] = vol
        
        return pd.Series(result, name=self.name)


class SimpleMovingAverage(BaseFeature):
    """Simple moving average."""
    
    def __init__(self, window: int = 50):
        self._window = window
    
    @property
    def name(self) -> str:
        return f"sma_{self._window}"
    
    @property
    def category(self) -> str:
        return "momentum"
    
    @property
    def dependencies(self) -> list[str]:
        return ["adj_close"]
    
    @property
    def lookback_days(self) -> int:
        return self._window
    
    def get_parameters(self) -> dict[str, Any]:
        return {"window": self._window}
    
    def calculate(
        self,
        data: pd.DataFrame,
        target_date: date,
        parameters: Optional[dict[str, Any]] = None,
    ) -> pd.Series:
        window = parameters.get("window", self._window) if parameters else self._window
        result = {}
        
        for instrument_id in data["instrument_id"].unique():
            inst_data = data[data["instrument_id"] == instrument_id].sort_values("trade_date")
            
            if len(inst_data) < window:
                result[instrument_id] = np.nan
                continue
            
            prices = inst_data["adj_close"].tail(window).values
            result[instrument_id] = np.mean(prices)
        
        return pd.Series(result, name=self.name)


class RSI(BaseFeature):
    """Relative Strength Index."""
    
    def __init__(self, window: int = 14):
        self._window = window
    
    @property
    def name(self) -> str:
        return f"rsi_{self._window}"
    
    @property
    def category(self) -> str:
        return "momentum"
    
    @property
    def dependencies(self) -> list[str]:
        return ["adj_close"]
    
    @property
    def lookback_days(self) -> int:
        return self._window + 1
    
    def get_parameters(self) -> dict[str, Any]:
        return {"window": self._window}
    
    def calculate(
        self,
        data: pd.DataFrame,
        target_date: date,
        parameters: Optional[dict[str, Any]] = None,
    ) -> pd.Series:
        window = parameters.get("window", self._window) if parameters else self._window
        result = {}
        
        for instrument_id in data["instrument_id"].unique():
            inst_data = data[data["instrument_id"] == instrument_id].sort_values("trade_date")
            
            if len(inst_data) < window + 1:
                result[instrument_id] = np.nan
                continue
            
            prices = inst_data["adj_close"].tail(window + 1).values
            deltas = np.diff(prices)
            
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)
            
            avg_gain = np.mean(gains)
            avg_loss = np.mean(losses)
            
            if avg_loss == 0:
                result[instrument_id] = 100.0
            else:
                rs = avg_gain / avg_loss
                result[instrument_id] = 100 - (100 / (1 + rs))
        
        return pd.Series(result, name=self.name)
