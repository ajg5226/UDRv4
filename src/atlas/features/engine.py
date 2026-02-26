"""Feature calculation engine."""

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Optional

import pandas as pd

from atlas.core.config import get_settings
from atlas.core.logging import get_logger
from atlas.features.base import BaseFeature, FeatureResult
from atlas.features.registry import FeatureRegistry, get_feature_registry
from atlas.storage.database import get_database
from atlas.storage.repository import FeatureRepository, OHLCVRepository

logger = get_logger(__name__)


@dataclass
class EngineResult:
    """Result of a feature calculation run."""
    
    target_date: date
    features_calculated: int
    instruments_processed: int
    
    # Results per feature
    feature_results: dict[str, FeatureResult] = field(default_factory=dict)
    
    # Timing
    total_time_ms: float = 0.0
    
    # Errors
    errors: list[str] = field(default_factory=list)
    
    @property
    def success(self) -> bool:
        """Check if all calculations succeeded."""
        return len(self.errors) == 0


class FeatureEngine:
    """
    Engine for calculating and persisting features.
    
    Handles:
    - Loading historical data for lookback
    - Calculating features in dependency order
    - Parallel calculation (optional)
    - Persisting results to database
    """
    
    def __init__(
        self,
        registry: Optional[FeatureRegistry] = None,
    ) -> None:
        self._registry = registry or get_feature_registry()
        self._settings = get_settings()
        self._db = get_database()
    
    async def calculate(
        self,
        target_date: date,
        feature_names: Optional[list[str]] = None,
        instrument_ids: Optional[list[int]] = None,
        persist: bool = True,
        run_id: Optional[int] = None,
    ) -> EngineResult:
        """
        Calculate features for a specific date.
        
        Args:
            target_date: Date to calculate features for
            feature_names: Specific features to calculate (None = all)
            instrument_ids: Specific instruments (None = all active)
            persist: Whether to persist results to database
            run_id: Pipeline run ID for tracking
            
        Returns:
            EngineResult with calculation details
        """
        start_time = datetime.utcnow()
        
        logger.info(
            "Starting feature calculation",
            target_date=str(target_date),
            feature_count=len(feature_names) if feature_names else "all",
        )
        
        result = EngineResult(
            target_date=target_date,
            features_calculated=0,
            instruments_processed=0,
        )
        
        try:
            # Get features in calculation order
            features = self._registry.get_calculation_order(feature_names)
            
            if not features:
                logger.warning("No features to calculate")
                return result
            
            # Determine required lookback
            max_lookback = max(f.lookback_days for f in features)
            start_date = target_date - timedelta(days=max_lookback + 10)  # Buffer
            
            # Load historical data
            data = await self._load_data(
                start_date, target_date, instrument_ids
            )
            
            if data.empty:
                logger.warning("No historical data available")
                return result
            
            result.instruments_processed = data["instrument_id"].nunique()
            
            # Calculate each feature
            for feature in features:
                try:
                    feature_result = await self._calculate_feature(
                        feature, data, target_date
                    )
                    result.feature_results[feature.name] = feature_result
                    result.features_calculated += 1
                    
                    # Add calculated feature to data for dependent features
                    if not feature_result.values.empty:
                        # Merge feature values back into data
                        pass  # Complex; simplified for now
                    
                except Exception as e:
                    logger.error(f"Failed to calculate {feature.name}", error=str(e))
                    result.errors.append(f"{feature.name}: {str(e)}")
            
            # Persist results
            if persist:
                await self._persist_results(result, run_id)
            
        except Exception as e:
            logger.error("Feature calculation failed", error=str(e))
            result.errors.append(str(e))
        
        result.total_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        logger.info(
            "Feature calculation complete",
            features_calculated=result.features_calculated,
            instruments=result.instruments_processed,
            time_ms=result.total_time_ms,
        )
        
        return result
    
    async def _load_data(
        self,
        start_date: date,
        end_date: date,
        instrument_ids: Optional[list[int]],
    ) -> pd.DataFrame:
        """Load historical OHLCV data for feature calculation."""
        with self._db.session() as session:
            repo = OHLCVRepository(session)
            data = repo.get_as_dataframe(
                instrument_ids=instrument_ids,
                start_date=start_date,
                end_date=end_date,
            )
        
        logger.debug(
            f"Loaded {len(data)} rows of historical data",
            start=str(start_date),
            end=str(end_date),
        )
        
        return data
    
    async def _calculate_feature(
        self,
        feature: BaseFeature,
        data: pd.DataFrame,
        target_date: date,
    ) -> FeatureResult:
        """Calculate a single feature."""
        start_time = datetime.utcnow()
        
        try:
            # Filter data to required lookback window
            lookback_start = target_date - timedelta(days=feature.lookback_days + 5)
            feature_data = data[
                (data["trade_date"] >= lookback_start) &
                (data["trade_date"] <= target_date)
            ].copy()
            
            # Calculate
            values = feature.calculate(feature_data, target_date)
            
            # Validate
            is_valid, validation_errors = feature.validate(values)
            
            elapsed_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            result = FeatureResult(
                feature_name=feature.name,
                trade_date=target_date,
                values=values,
                calculation_time_ms=elapsed_ms,
                instruments_calculated=len(values.dropna()),
                instruments_failed=values.isna().sum(),
                errors=validation_errors,
            )
            
            logger.debug(
                f"Calculated {feature.name}",
                instruments=result.instruments_calculated,
                time_ms=elapsed_ms,
            )
            
            return result
            
        except Exception as e:
            elapsed_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            return FeatureResult(
                feature_name=feature.name,
                trade_date=target_date,
                values=pd.Series(dtype=float),
                calculation_time_ms=elapsed_ms,
                errors=[str(e)],
            )
    
    async def _persist_results(
        self,
        result: EngineResult,
        run_id: Optional[int],
    ) -> None:
        """Persist calculated features to database."""
        records = []
        
        for feature_name, feature_result in result.feature_results.items():
            if feature_result.values.empty:
                continue
            
            for instrument_id, value in feature_result.values.items():
                if pd.notna(value):
                    records.append({
                        "instrument_id": instrument_id,
                        "trade_date": result.target_date,
                        "feature_name": feature_name,
                        "value": float(value),
                    })
        
        if not records:
            logger.debug("No feature records to persist")
            return
        
        with self._db.session() as session:
            repo = FeatureRepository(session)
            inserted, updated = repo.upsert_batch(records, run_id)
        
        logger.info(
            f"Persisted features",
            inserted=inserted,
            updated=updated,
        )
    
    async def calculate_backfill(
        self,
        start_date: date,
        end_date: date,
        feature_names: Optional[list[str]] = None,
        instrument_ids: Optional[list[int]] = None,
        batch_size: int = 30,
    ) -> list[EngineResult]:
        """
        Calculate features for a date range (backfill).
        
        Args:
            start_date: Start date
            end_date: End date
            feature_names: Features to calculate
            instrument_ids: Instruments to process
            batch_size: Days per batch
            
        Returns:
            List of EngineResults, one per date
        """
        results = []
        current = start_date
        
        while current <= end_date:
            # Skip weekends
            if current.weekday() < 5:
                result = await self.calculate(
                    target_date=current,
                    feature_names=feature_names,
                    instrument_ids=instrument_ids,
                    persist=True,
                )
                results.append(result)
            
            current += timedelta(days=1)
        
        return results
