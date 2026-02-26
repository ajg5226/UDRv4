"""
Feature Generators - Calculation implementations for each feature family.

Each generator implements the raw calculation logic. Transforms (rank, zscore)
are applied in the panel transformation layer.
"""

from abc import ABC, abstractmethod
from datetime import date, timedelta
from typing import Any, Optional

import numpy as np
import pandas as pd
from scipy import stats

from atlas.core.logging import get_logger
from atlas.features.schema import (
    FeatureDefinition,
    FeatureFamily,
    BENCHMARK_CONFIG,
    FACTOR_ETF_CONFIG,
)

logger = get_logger(__name__)


class BaseGenerator(ABC):
    """Base class for feature generators."""
    
    @property
    @abstractmethod
    def family(self) -> FeatureFamily:
        """Feature family this generator handles."""
        pass
    
    @abstractmethod
    def calculate(
        self,
        feature: FeatureDefinition,
        data: pd.DataFrame,
        lookback: int,
        target_date: date,
        benchmark_data: Optional[pd.DataFrame] = None,
        factor_data: Optional[dict[str, pd.DataFrame]] = None,
    ) -> pd.Series:
        """
        Calculate feature values for all instruments.
        
        Args:
            feature: Feature definition
            data: OHLCV data with columns [instrument_id, trade_date, adj_close, ...]
            lookback: Lookback period in days
            target_date: Date to calculate for
            benchmark_data: Benchmark OHLCV (for beta, capture, etc.)
            factor_data: Dict of factor ETF name -> OHLCV data
            
        Returns:
            Series indexed by instrument_id with feature values
        """
        pass
    
    def _get_returns(self, prices: pd.Series) -> pd.Series:
        """Calculate simple returns from prices."""
        return prices.pct_change()
    
    def _get_log_returns(self, prices: pd.Series) -> pd.Series:
        """Calculate log returns from prices."""
        return np.log(prices / prices.shift(1))
    
    def _filter_to_lookback(
        self,
        data: pd.DataFrame,
        instrument_id: int,
        target_date: date,
        lookback: int,
        buffer: int = 10,
    ) -> pd.DataFrame:
        """Filter data to lookback window for an instrument."""
        start_date = target_date - timedelta(days=lookback + buffer)
        mask = (
            (data["instrument_id"] == instrument_id) &
            (data["trade_date"] >= start_date) &
            (data["trade_date"] <= target_date)
        )
        return data[mask].sort_values("trade_date")


class MomentumGenerator(BaseGenerator):
    """Generator for momentum family features."""
    
    @property
    def family(self) -> FeatureFamily:
        return FeatureFamily.MOMENTUM
    
    def calculate(
        self,
        feature: FeatureDefinition,
        data: pd.DataFrame,
        lookback: int,
        target_date: date,
        benchmark_data: Optional[pd.DataFrame] = None,
        factor_data: Optional[dict[str, pd.DataFrame]] = None,
    ) -> pd.Series:
        results = {}
        
        for instrument_id in data["instrument_id"].unique():
            inst_data = self._filter_to_lookback(data, instrument_id, target_date, lookback)
            
            if len(inst_data) < lookback:
                results[instrument_id] = np.nan
                continue
            
            prices = inst_data["adj_close"].values
            
            if feature.name == "mom_ts":
                # Time-series momentum: cumulative return
                if prices[0] != 0 and not np.isnan(prices[0]):
                    results[instrument_id] = (prices[-1] - prices[-lookback]) / prices[-lookback]
                else:
                    results[instrument_id] = np.nan
                    
            elif feature.name == "mom_risk_adj":
                # Risk-adjusted momentum: return / vol
                returns = np.diff(np.log(prices[-lookback-1:]))
                if len(returns) >= lookback:
                    mom = (prices[-1] - prices[-lookback]) / prices[-lookback]
                    vol = np.std(returns) * np.sqrt(252)
                    results[instrument_id] = mom / vol if vol > 0 else np.nan
                else:
                    results[instrument_id] = np.nan
                    
            elif feature.name == "mom_intermediate":
                # Intermediate momentum: 63d / 21d
                if len(prices) >= 63:
                    mom_63 = (prices[-1] - prices[-63]) / prices[-63] if prices[-63] != 0 else 0
                    mom_21 = (prices[-1] - prices[-21]) / prices[-21] if prices[-21] != 0 else 0
                    results[instrument_id] = mom_63 / mom_21 if mom_21 != 0 else np.nan
                else:
                    results[instrument_id] = np.nan
                    
            elif feature.name == "mom_residual":
                # Residual momentum - needs factor data
                if factor_data is None:
                    results[instrument_id] = np.nan
                    continue
                    
                # Calculate returns
                inst_returns = self._get_returns(inst_data.set_index("trade_date")["adj_close"])
                
                # Get factor returns and run regression
                # Simplified: just strip SPY beta for now
                if "SPY" in factor_data:
                    spy_data = factor_data["SPY"]
                    spy_returns = self._get_returns(spy_data.set_index("trade_date")["adj_close"])
                    
                    # Align dates
                    aligned = pd.concat([inst_returns, spy_returns], axis=1, join="inner")
                    aligned.columns = ["inst", "spy"]
                    aligned = aligned.dropna().tail(lookback)
                    
                    if len(aligned) >= lookback // 2:
                        # Regress and get residual
                        slope, intercept, _, _, _ = stats.linregress(aligned["spy"], aligned["inst"])
                        residual_returns = aligned["inst"] - (intercept + slope * aligned["spy"])
                        results[instrument_id] = residual_returns.sum()  # Cumulative residual
                    else:
                        results[instrument_id] = np.nan
                else:
                    results[instrument_id] = np.nan
            else:
                results[instrument_id] = np.nan
        
        return pd.Series(results, name=feature.get_full_name(lookback))


class TrendGenerator(BaseGenerator):
    """Generator for trend quality features."""
    
    @property
    def family(self) -> FeatureFamily:
        return FeatureFamily.TREND
    
    def calculate(
        self,
        feature: FeatureDefinition,
        data: pd.DataFrame,
        lookback: int,
        target_date: date,
        benchmark_data: Optional[pd.DataFrame] = None,
        factor_data: Optional[dict[str, pd.DataFrame]] = None,
    ) -> pd.Series:
        results = {}
        
        for instrument_id in data["instrument_id"].unique():
            inst_data = self._filter_to_lookback(data, instrument_id, target_date, lookback)
            
            if len(inst_data) < lookback:
                results[instrument_id] = np.nan
                continue
            
            prices = inst_data["adj_close"].values
            highs = inst_data["high"].values if "high" in inst_data.columns else prices
            lows = inst_data["low"].values if "low" in inst_data.columns else prices
            
            if feature.name == "trend_slope":
                # MA slope of log-price
                log_prices = np.log(prices[-lookback:])
                x = np.arange(lookback)
                slope, _, _, _, _ = stats.linregress(x, log_prices)
                results[instrument_id] = slope * 252  # Annualized
                
            elif feature.name == "trend_adx":
                # Average Directional Index
                adx = self._calculate_adx(highs, lows, prices, lookback)
                results[instrument_id] = adx
                
            elif feature.name == "trend_efficiency":
                # Trend efficiency: net move / total path
                net_move = abs(prices[-1] - prices[-lookback])
                total_path = np.sum(np.abs(np.diff(prices[-lookback:])))
                results[instrument_id] = net_move / total_path if total_path > 0 else 0
                
            elif feature.name == "trend_choppiness":
                # Choppiness index
                tr_sum = np.sum(np.maximum(
                    highs[-lookback:] - lows[-lookback:],
                    np.maximum(
                        np.abs(highs[-lookback:] - np.roll(prices[-lookback:], 1)[1:lookback+1]),
                        np.abs(lows[-lookback:] - np.roll(prices[-lookback:], 1)[1:lookback+1])
                    )
                ))
                high_low_range = np.max(highs[-lookback:]) - np.min(lows[-lookback:])
                if high_low_range > 0:
                    chop = 100 * np.log10(tr_sum / high_low_range) / np.log10(lookback)
                    results[instrument_id] = chop
                else:
                    results[instrument_id] = np.nan
            else:
                results[instrument_id] = np.nan
        
        return pd.Series(results, name=feature.get_full_name(lookback))
    
    def _calculate_adx(self, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int) -> float:
        """Calculate ADX."""
        if len(highs) < period + 1:
            return np.nan
        
        # True Range
        tr = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(
                np.abs(highs[1:] - closes[:-1]),
                np.abs(lows[1:] - closes[:-1])
            )
        )
        
        # Directional Movement
        up_move = highs[1:] - highs[:-1]
        down_move = lows[:-1] - lows[1:]
        
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
        
        # Smoothed averages (simple EMA approximation)
        atr = pd.Series(tr).ewm(span=period, adjust=False).mean().iloc[-1]
        plus_di = 100 * pd.Series(plus_dm).ewm(span=period, adjust=False).mean().iloc[-1] / atr
        minus_di = 100 * pd.Series(minus_dm).ewm(span=period, adjust=False).mean().iloc[-1] / atr
        
        # ADX
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di) if (plus_di + minus_di) > 0 else 0
        
        return dx


class BreakoutGenerator(BaseGenerator):
    """Generator for breakout features."""
    
    @property
    def family(self) -> FeatureFamily:
        return FeatureFamily.BREAKOUT
    
    def calculate(
        self,
        feature: FeatureDefinition,
        data: pd.DataFrame,
        lookback: int,
        target_date: date,
        benchmark_data: Optional[pd.DataFrame] = None,
        factor_data: Optional[dict[str, pd.DataFrame]] = None,
    ) -> pd.Series:
        results = {}
        
        for instrument_id in data["instrument_id"].unique():
            inst_data = self._filter_to_lookback(data, instrument_id, target_date, lookback)
            
            if len(inst_data) < lookback:
                results[instrument_id] = np.nan
                continue
            
            prices = inst_data["adj_close"].values
            highs = inst_data["high"].values if "high" in inst_data.columns else prices
            lows = inst_data["low"].values if "low" in inst_data.columns else prices
            
            current_price = prices[-1]
            period_high = np.max(highs[-lookback:])
            period_low = np.min(lows[-lookback:])
            
            if feature.name == "breakout_high":
                # At N-day high (binary)
                results[instrument_id] = 1.0 if current_price >= period_high else 0.0
                
            elif feature.name == "breakout_dist_high":
                # Distance from N-day high (%)
                if period_high > 0:
                    results[instrument_id] = (current_price - period_high) / period_high
                else:
                    results[instrument_id] = np.nan
                    
            elif feature.name == "breakout_dist_low":
                # Distance from N-day low (%)
                if period_low > 0:
                    results[instrument_id] = (current_price - period_low) / period_low
                else:
                    results[instrument_id] = np.nan
            else:
                results[instrument_id] = np.nan
        
        return pd.Series(results, name=feature.get_full_name(lookback))


class MeanReversionGenerator(BaseGenerator):
    """Generator for mean reversion features."""
    
    @property
    def family(self) -> FeatureFamily:
        return FeatureFamily.MEAN_REVERSION
    
    def calculate(
        self,
        feature: FeatureDefinition,
        data: pd.DataFrame,
        lookback: int,
        target_date: date,
        benchmark_data: Optional[pd.DataFrame] = None,
        factor_data: Optional[dict[str, pd.DataFrame]] = None,
    ) -> pd.Series:
        results = {}
        
        for instrument_id in data["instrument_id"].unique():
            inst_data = self._filter_to_lookback(data, instrument_id, target_date, max(lookback, 200))
            
            if len(inst_data) < lookback:
                results[instrument_id] = np.nan
                continue
            
            prices = inst_data["adj_close"].values
            
            if feature.name == "mr_zscore":
                # Distance from mean z-score
                sma = np.mean(prices[-lookback:])
                std = np.std(prices[-lookback:])
                if std > 0:
                    results[instrument_id] = (prices[-1] - sma) / std
                else:
                    results[instrument_id] = np.nan
                    
            elif feature.name == "mr_reversal":
                # Short-term return reversal
                if len(prices) >= lookback + 1:
                    ret = (prices[-1] - prices[-lookback-1]) / prices[-lookback-1]
                    results[instrument_id] = ret
                else:
                    results[instrument_id] = np.nan
                    
            elif feature.name == "mr_dip_in_uptrend":
                # Pullback in uptrend: price > 200d MA AND zscore(20) < 0
                if len(prices) >= 200:
                    ma_200 = np.mean(prices[-200:])
                    sma_20 = np.mean(prices[-20:])
                    std_20 = np.std(prices[-20:])
                    zscore_20 = (prices[-1] - sma_20) / std_20 if std_20 > 0 else 0
                    
                    # Binary: 1 if dip in uptrend, 0 otherwise
                    is_uptrend = prices[-1] > ma_200
                    is_dip = zscore_20 < 0
                    results[instrument_id] = 1.0 if (is_uptrend and is_dip) else 0.0
                else:
                    results[instrument_id] = np.nan
                    
            elif feature.name == "mr_rsi":
                # RSI
                rsi = self._calculate_rsi(prices, lookback)
                results[instrument_id] = rsi
            else:
                results[instrument_id] = np.nan
        
        return pd.Series(results, name=feature.get_full_name(lookback))
    
    def _calculate_rsi(self, prices: np.ndarray, period: int) -> float:
        """Calculate RSI."""
        if len(prices) < period + 1:
            return np.nan
        
        deltas = np.diff(prices[-(period+1):])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))


class FactorGenerator(BaseGenerator):
    """Generator for factor proxy features."""
    
    @property
    def family(self) -> FeatureFamily:
        return FeatureFamily.FACTOR
    
    def calculate(
        self,
        feature: FeatureDefinition,
        data: pd.DataFrame,
        lookback: int,
        target_date: date,
        benchmark_data: Optional[pd.DataFrame] = None,
        factor_data: Optional[dict[str, pd.DataFrame]] = None,
    ) -> pd.Series:
        results = {}
        
        if factor_data is None:
            logger.warning(f"Factor data not provided for {feature.name}")
            return pd.Series(dtype=float)
        
        # Get the factor ETF for this feature
        factor_etf = feature.parameters.get("factor_etf", "SPY")
        
        if factor_etf not in factor_data:
            logger.warning(f"Factor ETF {factor_etf} not in factor_data")
            return pd.Series(dtype=float)
        
        factor_df = factor_data[factor_etf]
        factor_returns = self._get_returns(
            factor_df.set_index("trade_date")["adj_close"]
        ).dropna()
        
        for instrument_id in data["instrument_id"].unique():
            inst_data = self._filter_to_lookback(data, instrument_id, target_date, lookback)
            
            if len(inst_data) < lookback // 2:
                results[instrument_id] = np.nan
                continue
            
            inst_returns = self._get_returns(
                inst_data.set_index("trade_date")["adj_close"]
            ).dropna()
            
            # Align dates
            aligned = pd.concat([inst_returns, factor_returns], axis=1, join="inner")
            aligned.columns = ["inst", "factor"]
            aligned = aligned.dropna().tail(lookback)
            
            if len(aligned) < lookback // 2:
                results[instrument_id] = np.nan
                continue
            
            if feature.name.startswith("factor_beta_"):
                # Rolling beta
                cov = aligned.cov().iloc[0, 1]
                var = aligned["factor"].var()
                results[instrument_id] = cov / var if var > 0 else np.nan
                
            elif feature.name == "factor_tilt_score":
                # This depends on other features - computed in feature engine
                results[instrument_id] = np.nan
            else:
                results[instrument_id] = np.nan
        
        return pd.Series(results, name=feature.get_full_name(lookback))


class RiskGenerator(BaseGenerator):
    """Generator for risk/stability features."""
    
    @property
    def family(self) -> FeatureFamily:
        return FeatureFamily.RISK
    
    def calculate(
        self,
        feature: FeatureDefinition,
        data: pd.DataFrame,
        lookback: int,
        target_date: date,
        benchmark_data: Optional[pd.DataFrame] = None,
        factor_data: Optional[dict[str, pd.DataFrame]] = None,
    ) -> pd.Series:
        results = {}
        
        for instrument_id in data["instrument_id"].unique():
            inst_data = self._filter_to_lookback(data, instrument_id, target_date, lookback)
            
            if len(inst_data) < lookback // 2:
                results[instrument_id] = np.nan
                continue
            
            prices = inst_data["adj_close"].values
            returns = np.diff(np.log(prices))
            
            if feature.name == "risk_realized_vol":
                # Realized volatility (annualized)
                if len(returns) >= lookback:
                    results[instrument_id] = np.std(returns[-lookback:]) * np.sqrt(252)
                else:
                    results[instrument_id] = np.nan
                    
            elif feature.name == "risk_idio_vol":
                # Idiosyncratic volatility
                if benchmark_data is None:
                    results[instrument_id] = np.nan
                    continue
                    
                inst_returns = self._get_returns(inst_data.set_index("trade_date")["adj_close"])
                bench_returns = self._get_returns(benchmark_data.set_index("trade_date")["adj_close"])
                
                aligned = pd.concat([inst_returns, bench_returns], axis=1, join="inner").dropna()
                aligned.columns = ["inst", "bench"]
                
                if len(aligned) >= lookback // 2:
                    slope, intercept, _, _, _ = stats.linregress(aligned["bench"], aligned["inst"])
                    residuals = aligned["inst"] - (intercept + slope * aligned["bench"])
                    results[instrument_id] = residuals.std() * np.sqrt(252)
                else:
                    results[instrument_id] = np.nan
                    
            elif feature.name == "risk_drawdown":
                # Maximum drawdown
                if len(prices) >= lookback:
                    rolling_max = np.maximum.accumulate(prices[-lookback:])
                    drawdowns = (prices[-lookback:] - rolling_max) / rolling_max
                    results[instrument_id] = np.min(drawdowns)
                else:
                    results[instrument_id] = np.nan
                    
            elif feature.name == "risk_downside_vol":
                # Downside semi-variance
                if len(returns) >= lookback:
                    negative_returns = returns[-lookback:][returns[-lookback:] < 0]
                    if len(negative_returns) > 0:
                        results[instrument_id] = np.std(negative_returns) * np.sqrt(252)
                    else:
                        results[instrument_id] = 0.0
                else:
                    results[instrument_id] = np.nan
                    
            elif feature.name == "risk_beta_trend":
                # Beta trend - computed from factor_beta_spy changes
                results[instrument_id] = np.nan  # Computed in feature engine
            else:
                results[instrument_id] = np.nan
        
        return pd.Series(results, name=feature.get_full_name(lookback))


class UDRGenerator(BaseGenerator):
    """Generator for UDR/capture features."""
    
    @property
    def family(self) -> FeatureFamily:
        return FeatureFamily.UDR
    
    def calculate(
        self,
        feature: FeatureDefinition,
        data: pd.DataFrame,
        lookback: int,
        target_date: date,
        benchmark_data: Optional[pd.DataFrame] = None,
        factor_data: Optional[dict[str, pd.DataFrame]] = None,
    ) -> pd.Series:
        results = {}
        
        if benchmark_data is None:
            logger.warning(f"Benchmark data not provided for {feature.name}")
            return pd.Series(dtype=float)
        
        bench_returns = self._get_returns(
            benchmark_data.set_index("trade_date")["adj_close"]
        ).dropna()
        
        for instrument_id in data["instrument_id"].unique():
            inst_data = self._filter_to_lookback(data, instrument_id, target_date, lookback)
            
            if len(inst_data) < lookback // 2:
                results[instrument_id] = np.nan
                continue
            
            inst_returns = self._get_returns(
                inst_data.set_index("trade_date")["adj_close"]
            ).dropna()
            
            # Align dates
            aligned = pd.concat([inst_returns, bench_returns], axis=1, join="inner")
            aligned.columns = ["inst", "bench"]
            aligned = aligned.dropna().tail(lookback)
            
            if len(aligned) < lookback // 2:
                results[instrument_id] = np.nan
                continue
            
            up_days = aligned[aligned["bench"] > 0]
            down_days = aligned[aligned["bench"] < 0]
            
            if feature.name == "udr_up_capture":
                if len(up_days) > 0 and up_days["bench"].sum() != 0:
                    results[instrument_id] = up_days["inst"].sum() / up_days["bench"].sum()
                else:
                    results[instrument_id] = np.nan
                    
            elif feature.name == "udr_down_capture":
                if len(down_days) > 0 and down_days["bench"].sum() != 0:
                    results[instrument_id] = down_days["inst"].sum() / down_days["bench"].sum()
                else:
                    results[instrument_id] = np.nan
                    
            elif feature.name == "udr_capture_asymmetry":
                # Up capture / down capture
                up_cap = up_days["inst"].sum() / up_days["bench"].sum() if len(up_days) > 0 and up_days["bench"].sum() != 0 else np.nan
                down_cap = down_days["inst"].sum() / down_days["bench"].sum() if len(down_days) > 0 and down_days["bench"].sum() != 0 else np.nan
                
                if not np.isnan(up_cap) and not np.isnan(down_cap) and down_cap != 0:
                    results[instrument_id] = up_cap / down_cap
                else:
                    results[instrument_id] = np.nan
                    
            elif feature.name == "udr_capture_delta":
                # Computed from changes in asymmetry
                results[instrument_id] = np.nan
            else:
                results[instrument_id] = np.nan
        
        return pd.Series(results, name=feature.get_full_name(lookback))


class RegimeGenerator(BaseGenerator):
    """Generator for regime indicators."""
    
    @property
    def family(self) -> FeatureFamily:
        return FeatureFamily.REGIME
    
    def calculate(
        self,
        feature: FeatureDefinition,
        data: pd.DataFrame,
        lookback: int,
        target_date: date,
        benchmark_data: Optional[pd.DataFrame] = None,
        factor_data: Optional[dict[str, pd.DataFrame]] = None,
    ) -> pd.Series:
        results = {}
        
        for instrument_id in data["instrument_id"].unique():
            inst_data = self._filter_to_lookback(data, instrument_id, target_date, lookback)
            
            if len(inst_data) < lookback // 2:
                results[instrument_id] = np.nan
                continue
            
            prices = inst_data["adj_close"].values
            
            if feature.name == "regime_hurst":
                # Hurst exponent
                hurst = self._calculate_hurst(prices, lookback)
                results[instrument_id] = hurst
                
            elif feature.name == "regime_variance_ratio":
                # Variance ratio test
                vr = self._calculate_variance_ratio(prices, lookback)
                results[instrument_id] = vr
                
            elif feature.name == "regime_vol_level":
                # Vol percentile (computed across history)
                results[instrument_id] = np.nan  # Computed in panel layer
                
            elif feature.name == "regime_corr_spy":
                # Correlation to SPY
                if benchmark_data is None:
                    results[instrument_id] = np.nan
                    continue
                    
                inst_returns = self._get_returns(inst_data.set_index("trade_date")["adj_close"])
                bench_returns = self._get_returns(benchmark_data.set_index("trade_date")["adj_close"])
                
                aligned = pd.concat([inst_returns, bench_returns], axis=1, join="inner").dropna()
                aligned.columns = ["inst", "bench"]
                aligned = aligned.tail(lookback)
                
                if len(aligned) >= lookback // 2:
                    results[instrument_id] = aligned["inst"].corr(aligned["bench"])
                else:
                    results[instrument_id] = np.nan
            else:
                results[instrument_id] = np.nan
        
        return pd.Series(results, name=feature.get_full_name(lookback))
    
    def _calculate_hurst(self, prices: np.ndarray, max_lag: int) -> float:
        """Calculate Hurst exponent using R/S method."""
        if len(prices) < max_lag:
            return np.nan
        
        log_prices = np.log(prices[-max_lag:])
        returns = np.diff(log_prices)
        
        # Simplified R/S calculation
        lags = [8, 16, 32, 64] if max_lag >= 64 else [8, 16, 32]
        rs_values = []
        
        for lag in lags:
            if lag > len(returns):
                continue
            n_chunks = len(returns) // lag
            if n_chunks < 1:
                continue
                
            rs_list = []
            for i in range(n_chunks):
                chunk = returns[i*lag:(i+1)*lag]
                mean_adj = chunk - np.mean(chunk)
                cumsum = np.cumsum(mean_adj)
                r = np.max(cumsum) - np.min(cumsum)
                s = np.std(chunk)
                if s > 0:
                    rs_list.append(r / s)
            
            if rs_list:
                rs_values.append((np.log(lag), np.log(np.mean(rs_list))))
        
        if len(rs_values) >= 2:
            x = [v[0] for v in rs_values]
            y = [v[1] for v in rs_values]
            slope, _, _, _, _ = stats.linregress(x, y)
            return slope
        
        return np.nan
    
    def _calculate_variance_ratio(self, prices: np.ndarray, period: int) -> float:
        """Calculate variance ratio."""
        if len(prices) < period + 1:
            return np.nan
        
        log_prices = np.log(prices[-period-1:])
        returns_1 = np.diff(log_prices)
        returns_q = log_prices[::5][1:] - log_prices[::5][:-1]  # 5-period returns
        
        if len(returns_1) < 2 or len(returns_q) < 2:
            return np.nan
        
        var_1 = np.var(returns_1)
        var_q = np.var(returns_q)
        
        if var_1 == 0:
            return np.nan
        
        # Variance ratio: var(q-period) / (q * var(1-period))
        return var_q / (5 * var_1)


# Generator registry
GENERATORS: dict[FeatureFamily, BaseGenerator] = {
    FeatureFamily.MOMENTUM: MomentumGenerator(),
    FeatureFamily.TREND: TrendGenerator(),
    FeatureFamily.BREAKOUT: BreakoutGenerator(),
    FeatureFamily.MEAN_REVERSION: MeanReversionGenerator(),
    FeatureFamily.FACTOR: FactorGenerator(),
    FeatureFamily.RISK: RiskGenerator(),
    FeatureFamily.UDR: UDRGenerator(),
    FeatureFamily.REGIME: RegimeGenerator(),
}


def get_generator(family: FeatureFamily) -> BaseGenerator:
    """Get the generator for a feature family."""
    return GENERATORS[family]
