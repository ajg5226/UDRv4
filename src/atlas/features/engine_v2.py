"""
Enhanced Feature Engine V2 - Production-grade feature calculation.

Integrates:
- Unified schema
- Parameterized generators
- Panel transformations (cross-sectional rank/zscore)
- Feature diagnostics
- Versioning and lineage
"""

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Optional

import numpy as np
import pandas as pd

from atlas.core.config import get_settings
from atlas.core.logging import get_logger
from atlas.features.schema import (
    FEATURE_CATALOG,
    FeatureDefinition,
    FeatureFamily,
    TransformType,
    DataRequirement,
    BENCHMARK_CONFIG,
    FACTOR_ETF_CONFIG,
    get_enabled_features,
    get_features_by_priority,
    count_total_features,
)
from atlas.features.generators import get_generator, GENERATORS
from atlas.features.transforms import PanelTransformer, TransformResult
from atlas.features.diagnostics import DiagnosticsCalculator, FeatureDiagnostic
from atlas.storage.database import get_database

logger = get_logger(__name__)


@dataclass
class FeatureEngineConfig:
    """Configuration for the feature engine."""
    
    # Feature selection
    max_priority: int = 3  # Include features up to this priority
    enabled_families: list[FeatureFamily] = None  # None = all
    
    # Transforms
    apply_transforms: bool = True
    
    # Diagnostics
    calculate_diagnostics: bool = True
    
    # Processing
    parallel: bool = True
    batch_size: int = 50  # Instruments per batch
    
    def __post_init__(self):
        if self.enabled_families is None:
            self.enabled_families = list(FeatureFamily)


@dataclass
class EngineRunResult:
    """Result of a feature engine run."""
    
    target_date: date
    start_time: datetime
    end_time: datetime
    
    # Counts
    features_calculated: int = 0
    instruments_processed: int = 0
    records_written: int = 0
    
    # Details
    feature_results: dict[str, int] = field(default_factory=dict)  # feature_name -> count
    
    # Errors
    errors: list[str] = field(default_factory=list)
    
    @property
    def duration_seconds(self) -> float:
        return (self.end_time - self.start_time).total_seconds()
    
    @property
    def success(self) -> bool:
        return len(self.errors) == 0


class FeatureEngineV2:
    """
    Production-grade feature calculation engine.
    
    This engine:
    1. Reads feature definitions from the unified schema
    2. Calculates raw features using family-specific generators
    3. Applies cross-sectional transforms (rank, zscore)
    4. Computes feature diagnostics (IC, hit rate)
    5. Persists everything with versioning and lineage
    """
    
    def __init__(self, config: FeatureEngineConfig = None):
        self.config = config or FeatureEngineConfig()
        self.db = get_database()
        self.transformer = PanelTransformer()
        self.diagnostics_calc = DiagnosticsCalculator()
        
        # Cache for benchmark and factor data
        self._benchmark_cache: dict[str, pd.DataFrame] = {}
        self._factor_cache: dict[str, pd.DataFrame] = {}
    
    async def calculate(
        self,
        target_date: date,
        instrument_ids: list[int] = None,
        run_id: int = None,
    ) -> EngineRunResult:
        """
        Calculate all enabled features for a target date.
        
        Args:
            target_date: Date to calculate features for
            instrument_ids: Specific instruments (None = all active)
            run_id: Pipeline run ID for tracking
            
        Returns:
            EngineRunResult with calculation details
        """
        start_time = datetime.utcnow()
        
        result = EngineRunResult(
            target_date=target_date,
            start_time=start_time,
            end_time=start_time,
        )
        
        logger.info(f"Starting feature calculation for {target_date}")
        
        try:
            # Get features to calculate
            features = get_features_by_priority(self.config.max_priority)
            features = [f for f in features if f.family in self.config.enabled_families]
            
            logger.info(f"Calculating {len(features)} base features")
            
            # Load OHLCV data
            ohlcv_data = await self._load_ohlcv_data(target_date, instrument_ids)
            
            if ohlcv_data.empty:
                result.errors.append("No OHLCV data available")
                result.end_time = datetime.utcnow()
                return result
            
            result.instruments_processed = ohlcv_data["instrument_id"].nunique()
            
            # Load benchmark and factor data
            benchmark_data = await self._load_benchmark_data(target_date)
            factor_data = await self._load_factor_data(target_date)
            
            # Calculate features by family
            all_raw_features = {}  # feature_full_name -> pd.Series (instrument_id -> value)
            
            for family in self.config.enabled_families:
                family_features = [f for f in features if f.family == family]
                if not family_features:
                    continue
                
                generator = get_generator(family)
                
                for feature in family_features:
                    try:
                        # Generate all lookback variants
                        for full_name, lookback, transform in feature.generate_variants():
                            # Only calculate raw values here; transforms applied later
                            if transform != TransformType.RAW:
                                continue
                            
                            raw_name = feature.get_full_name(lookback, TransformType.RAW)
                            
                            values = generator.calculate(
                                feature=feature,
                                data=ohlcv_data,
                                lookback=lookback,
                                target_date=target_date,
                                benchmark_data=benchmark_data,
                                factor_data=factor_data,
                            )
                            
                            if not values.empty:
                                all_raw_features[raw_name] = values
                                result.feature_results[raw_name] = len(values.dropna())
                        
                    except Exception as e:
                        logger.error(f"Error calculating {feature.name}: {e}")
                        result.errors.append(f"{feature.name}: {str(e)}")
            
            # Apply cross-sectional transforms
            if self.config.apply_transforms and all_raw_features:
                transformed_features = await self._apply_transforms(
                    all_raw_features, features, target_date
                )
                all_raw_features.update(transformed_features)
            
            result.features_calculated = len(all_raw_features)
            
            # Persist features
            if all_raw_features:
                records_written = await self._persist_features(
                    all_raw_features, target_date, run_id
                )
                result.records_written = records_written
            
            # Calculate diagnostics (if we have enough history)
            if self.config.calculate_diagnostics:
                await self._calculate_and_store_diagnostics(
                    all_raw_features, ohlcv_data, target_date, run_id
                )
            
        except Exception as e:
            logger.error(f"Feature engine error: {e}")
            result.errors.append(str(e))
        
        result.end_time = datetime.utcnow()
        
        logger.info(
            f"Feature calculation complete",
            features=result.features_calculated,
            instruments=result.instruments_processed,
            records=result.records_written,
            duration=result.duration_seconds,
        )
        
        return result
    
    async def _load_ohlcv_data(
        self,
        target_date: date,
        instrument_ids: list[int] = None,
    ) -> pd.DataFrame:
        """Load OHLCV data with sufficient history."""
        # Get max lookback needed
        max_lookback = max(f.min_history for f in get_enabled_features())
        start_date = target_date - timedelta(days=max_lookback + 30)
        
        with self.db.session() as session:
            from atlas.storage.repository import OHLCVRepository
            repo = OHLCVRepository(session)
            data = repo.get_as_dataframe(
                instrument_ids=instrument_ids,
                start_date=start_date,
                end_date=target_date,
            )
        
        # Ensure we have high/low columns (use close if not available)
        if "high" not in data.columns:
            data["high"] = data["adj_close"]
        if "low" not in data.columns:
            data["low"] = data["adj_close"]
        
        return data
    
    async def _load_benchmark_data(self, target_date: date) -> Optional[pd.DataFrame]:
        """Load benchmark (SPY) data."""
        benchmark_ticker = BENCHMARK_CONFIG["primary"]
        
        if benchmark_ticker in self._benchmark_cache:
            return self._benchmark_cache[benchmark_ticker]
        
        # Load from database
        with self.db.session() as session:
            from atlas.storage.repository import InstrumentRepository, OHLCVRepository
            
            inst_repo = InstrumentRepository(session)
            ohlcv_repo = OHLCVRepository(session)
            
            benchmark_inst = inst_repo.get_by_ticker(benchmark_ticker)
            if benchmark_inst is None:
                logger.warning(f"Benchmark {benchmark_ticker} not found in database")
                return None
            
            max_lookback = max(f.min_history for f in get_enabled_features())
            start_date = target_date - timedelta(days=max_lookback + 30)
            
            data = ohlcv_repo.get_as_dataframe(
                instrument_ids=[benchmark_inst.instrument_id],
                start_date=start_date,
                end_date=target_date,
            )
        
        self._benchmark_cache[benchmark_ticker] = data
        return data
    
    async def _load_factor_data(self, target_date: date) -> dict[str, pd.DataFrame]:
        """Load factor ETF data."""
        factor_data = {}
        
        with self.db.session() as session:
            from atlas.storage.repository import InstrumentRepository, OHLCVRepository
            
            inst_repo = InstrumentRepository(session)
            ohlcv_repo = OHLCVRepository(session)
            
            max_lookback = max(f.min_history for f in get_enabled_features())
            start_date = target_date - timedelta(days=max_lookback + 30)
            
            for factor_name, ticker in FACTOR_ETF_CONFIG.items():
                if ticker in self._factor_cache:
                    factor_data[ticker] = self._factor_cache[ticker]
                    continue
                
                inst = inst_repo.get_by_ticker(ticker)
                if inst is None:
                    continue
                
                data = ohlcv_repo.get_as_dataframe(
                    instrument_ids=[inst.instrument_id],
                    start_date=start_date,
                    end_date=target_date,
                )
                
                if not data.empty:
                    factor_data[ticker] = data
                    self._factor_cache[ticker] = data
        
        return factor_data
    
    async def _apply_transforms(
        self,
        raw_features: dict[str, pd.Series],
        feature_defs: list[FeatureDefinition],
        target_date: date,
    ) -> dict[str, pd.Series]:
        """Apply cross-sectional transforms to raw features."""
        transformed = {}
        
        # Build lookup from raw feature name to definition
        name_to_def = {}
        for feature in feature_defs:
            for full_name, lookback, transform in feature.generate_variants():
                if transform == TransformType.RAW:
                    name_to_def[full_name] = (feature, lookback)
        
        for raw_name, raw_values in raw_features.items():
            if raw_name not in name_to_def:
                continue
            
            feature_def, lookback = name_to_def[raw_name]
            
            # Apply each non-raw transform defined for this feature
            for transform in feature_def.transforms:
                if transform == TransformType.RAW:
                    continue
                
                result = self.transformer.transform(
                    raw_values,
                    transform,
                    feature_def.get_full_name(lookback, TransformType.RAW),
                    target_date,
                )
                
                transformed[result.feature_name] = result.values
        
        return transformed
    
    async def _persist_features(
        self,
        features: dict[str, pd.Series],
        target_date: date,
        run_id: int = None,
    ) -> int:
        """Persist calculated features to database."""
        records = []
        calc_timestamp = datetime.utcnow()
        
        for feature_name, values in features.items():
            # Determine version and transform type from name
            version = "1.0.0"
            transform_type = "raw"
            for t in ["_rank", "_zscore", "_quintile", "_decile"]:
                if feature_name.endswith(t):
                    transform_type = t[1:]
                    break
            
            # Create hash of parameters (simplified)
            params_hash = hashlib.md5(feature_name.encode()).hexdigest()[:16]
            
            for instrument_id, value in values.items():
                if pd.notna(value):
                    records.append({
                        "instrument_id": instrument_id,
                        "trade_date": target_date,
                        "feature_name": feature_name,
                        "value": float(value),
                        "feature_version": version,
                        "params_hash": params_hash,
                        "transform_type": transform_type,
                        "calc_timestamp": calc_timestamp,
                        "run_id": run_id,
                    })
        
        if not records:
            return 0
        
        with self.db.session() as session:
            from atlas.storage.repository import FeatureRepository
            repo = FeatureRepository(session)
            inserted, updated = repo.upsert_batch(records, run_id)
        
        return inserted + updated
    
    async def _calculate_and_store_diagnostics(
        self,
        features: dict[str, pd.Series],
        price_data: pd.DataFrame,
        target_date: date,
        run_id: int = None,
    ) -> None:
        """Calculate and store feature diagnostics."""
        # For now, skip diagnostics if we don't have enough future data
        # In production, this would run on a lag (e.g., calculate diagnostics for T-21 using T data)
        logger.debug("Diagnostics calculation deferred (requires future returns data)")
        pass
    
    def clear_cache(self) -> None:
        """Clear the benchmark and factor data cache."""
        self._benchmark_cache.clear()
        self._factor_cache.clear()


# Convenience function
async def calculate_features(
    target_date: date,
    instrument_ids: list[int] = None,
    run_id: int = None,
    config: FeatureEngineConfig = None,
) -> EngineRunResult:
    """
    Calculate features for a target date.
    
    Convenience wrapper around FeatureEngineV2.
    """
    engine = FeatureEngineV2(config)
    return await engine.calculate(target_date, instrument_ids, run_id)
