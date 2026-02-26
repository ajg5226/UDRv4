"""Pipeline orchestrator for coordinating data ingestion."""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any, Optional

import pandas as pd

from atlas.core.config import get_settings
from atlas.core.exceptions import PipelineError, ProviderError
from atlas.core.logging import get_logger, bind_context, clear_context
from atlas.providers.base import ProviderResult, ProviderType
from atlas.providers.registry import get_provider_registry, setup_providers
from atlas.storage.database import get_database
from atlas.storage.repository import (
    InstrumentRepository,
    MacroRepository,
    MacroSeriesRepository,
    OHLCVRepository,
    PipelineRunRepository,
    SourceRepository,
)

logger = get_logger(__name__)


class RunType(str, Enum):
    """Types of pipeline runs."""
    
    NIGHTLY = "nightly"
    BACKFILL = "backfill"
    MANUAL = "manual"


class RunStatus(str, Enum):
    """Pipeline run status values."""
    
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass
class RunConfig:
    """Configuration for a pipeline run."""
    
    run_type: RunType = RunType.MANUAL
    target_date: Optional[date] = None
    providers: Optional[list[str]] = None
    instruments: Optional[list[str]] = None
    tags: Optional[list[str]] = None
    skip_features: bool = False
    parallel: bool = True
    
    def __post_init__(self) -> None:
        if self.target_date is None:
            # Default to previous business day
            self.target_date = self._get_previous_business_day()
    
    @staticmethod
    def _get_previous_business_day() -> date:
        """Get the previous business day."""
        today = date.today()
        offset = 1
        if today.weekday() == 0:  # Monday
            offset = 3
        elif today.weekday() == 6:  # Sunday
            offset = 2
        return today - timedelta(days=offset)


@dataclass
class RunResult:
    """Result of a pipeline run."""
    
    run_id: int
    status: RunStatus
    run_date: date
    start_time: datetime
    end_time: datetime
    
    # Counts
    records_inserted: int = 0
    records_updated: int = 0
    
    # Provider results
    provider_results: dict[str, ProviderResult] = field(default_factory=dict)
    
    # Errors
    errors: list[str] = field(default_factory=list)
    
    @property
    def duration_seconds(self) -> float:
        """Get run duration in seconds."""
        return (self.end_time - self.start_time).total_seconds()
    
    @property
    def success(self) -> bool:
        """Check if run was fully successful."""
        return self.status == RunStatus.SUCCESS


class PipelineOrchestrator:
    """
    Main pipeline orchestrator.
    
    Coordinates:
    - Provider execution (parallel or sequential)
    - Data validation
    - Database persistence
    - Feature calculation
    - Error handling and recovery
    """
    
    def __init__(self) -> None:
        self._settings = get_settings()
        self._db = get_database()
        self._registry = get_provider_registry()
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize the orchestrator and all providers."""
        if self._initialized:
            return
        
        logger.info("Initializing pipeline orchestrator")
        
        # Setup database tables
        self._db.create_tables()
        
        # Setup providers
        await setup_providers()
        
        self._initialized = True
        logger.info("Pipeline orchestrator initialized")
    
    async def run(self, config: Optional[RunConfig] = None) -> RunResult:
        """
        Execute a pipeline run.
        
        Args:
            config: Run configuration. If None, uses defaults.
            
        Returns:
            RunResult with execution details
        """
        if not self._initialized:
            await self.initialize()
        
        config = config or RunConfig()
        start_time = datetime.utcnow()
        
        # Bind logging context
        bind_context(
            run_type=config.run_type.value,
            run_date=str(config.target_date),
        )
        
        logger.info(
            "Starting pipeline run",
            providers=config.providers,
            tags=config.tags,
        )
        
        try:
            # Create run record
            with self._db.session() as session:
                run_repo = PipelineRunRepository(session)
                run = run_repo.create_run(
                    run_type=config.run_type.value,
                    run_date=config.target_date,
                    providers=config.providers,
                    tags_filter=config.tags,
                )
                run_id = run.run_id
            
            bind_context(run_id=run_id)
            
            # Get providers to run
            providers = self._get_providers(config.providers)
            
            # Get instruments (filtered by tags if specified)
            instruments = await self._get_instruments(config)
            
            # Execute providers
            if config.parallel and len(providers) > 1:
                provider_results = await self._run_providers_parallel(
                    providers, config.target_date, instruments
                )
            else:
                provider_results = await self._run_providers_sequential(
                    providers, config.target_date, instruments
                )
            
            # Persist results
            total_inserted, total_updated, errors = await self._persist_results(
                provider_results, run_id
            )
            
            # Calculate features (if enabled)
            if not config.skip_features and self._settings.features.enabled:
                await self._calculate_features(config.target_date, instruments, run_id)
            
            # Determine final status
            status = self._determine_status(provider_results, errors)
            
            # Update run record
            with self._db.session() as session:
                run_repo = PipelineRunRepository(session)
                run_repo.complete_run(
                    run_id=run_id,
                    status=status.value,
                    records_inserted=total_inserted,
                    records_updated=total_updated,
                    errors="\n".join(errors) if errors else None,
                )
            
            end_time = datetime.utcnow()
            
            result = RunResult(
                run_id=run_id,
                status=status,
                run_date=config.target_date,
                start_time=start_time,
                end_time=end_time,
                records_inserted=total_inserted,
                records_updated=total_updated,
                provider_results=provider_results,
                errors=errors,
            )
            
            logger.info(
                "Pipeline run complete",
                status=status.value,
                records_inserted=total_inserted,
                records_updated=total_updated,
                duration_seconds=result.duration_seconds,
            )
            
            return result
            
        except Exception as e:
            logger.error("Pipeline run failed", error=str(e))
            
            # Try to update run record with failure
            try:
                with self._db.session() as session:
                    run_repo = PipelineRunRepository(session)
                    run_repo.complete_run(
                        run_id=run_id,
                        status=RunStatus.FAILED.value,
                        errors=str(e),
                    )
            except Exception:
                pass
            
            raise PipelineError(
                "Pipeline execution failed",
                run_id=run_id,
                cause=e,
            ) from e
            
        finally:
            clear_context()
    
    def _get_providers(self, provider_names: Optional[list[str]]) -> list:
        """Get providers to execute."""
        if provider_names:
            return [self._registry.get(name) for name in provider_names]
        
        # Use default providers from config
        default_providers = self._settings.pipeline.default_providers
        return [
            self._registry.get(name)
            for name in default_providers
            if self._registry.has(name)
        ]
    
    async def _get_instruments(self, config: RunConfig) -> Optional[list[str]]:
        """Get instruments to fetch data for."""
        # If specific instruments provided, use those
        if config.instruments:
            return config.instruments
        
        # If tags specified, get instruments with those tags
        if config.tags:
            with self._db.session() as session:
                repo = InstrumentRepository(session)
                instruments = repo.get_by_tags(config.tags)
                return [i.ticker for i in instruments]
        
        # Otherwise return None (fetch all)
        return None
    
    async def _run_providers_parallel(
        self,
        providers: list,
        target_date: date,
        instruments: Optional[list[str]],
    ) -> dict[str, ProviderResult]:
        """Run providers in parallel."""
        tasks = []
        for provider in providers:
            task = self._run_single_provider(provider, target_date, instruments)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        provider_results = {}
        for provider, result in zip(providers, results):
            if isinstance(result, Exception):
                logger.error(f"Provider {provider.name} failed", error=str(result))
                # Create a failed result
                provider_results[provider.name] = ProviderResult(
                    provider_name=provider.name,
                    fetch_date=target_date,
                    data=pd.DataFrame(),
                    success=False,
                    error_message=str(result),
                )
            else:
                provider_results[provider.name] = result
        
        return provider_results
    
    async def _run_providers_sequential(
        self,
        providers: list,
        target_date: date,
        instruments: Optional[list[str]],
    ) -> dict[str, ProviderResult]:
        """Run providers sequentially."""
        provider_results = {}
        
        for provider in providers:
            try:
                result = await self._run_single_provider(provider, target_date, instruments)
                provider_results[provider.name] = result
            except Exception as e:
                logger.error(f"Provider {provider.name} failed", error=str(e))
                provider_results[provider.name] = ProviderResult(
                    provider_name=provider.name,
                    fetch_date=target_date,
                    data=pd.DataFrame(),
                    success=False,
                    error_message=str(e),
                )
        
        return provider_results
    
    async def _run_single_provider(
        self,
        provider,
        target_date: date,
        instruments: Optional[list[str]],
    ) -> ProviderResult:
        """Run a single provider."""
        logger.info(f"Running provider: {provider.name}")
        
        # For macro providers, don't pass instruments (they have their own series)
        if provider.provider_type == ProviderType.MACRO:
            result = await provider.fetch_data(target_date)
        else:
            result = await provider.fetch_data(target_date, instruments)
        
        if result.validation and not result.validation.is_valid:
            logger.warning(
                f"Provider {provider.name} validation issues",
                validation=result.validation.message,
            )
        
        return result
    
    async def _persist_results(
        self,
        provider_results: dict[str, ProviderResult],
        run_id: int,
    ) -> tuple[int, int, list[str]]:
        """Persist provider results to database."""
        total_inserted = 0
        total_updated = 0
        errors = []
        
        with self._db.session() as session:
            source_repo = SourceRepository(session)
            instrument_repo = InstrumentRepository(session)
            ohlcv_repo = OHLCVRepository(session)
            macro_repo = MacroRepository(session)
            macro_series_repo = MacroSeriesRepository(session)
            
            for provider_name, result in provider_results.items():
                if not result.success and not result.partial_failure:
                    if result.error_message:
                        errors.append(f"{provider_name}: {result.error_message}")
                    continue
                
                if result.data.empty:
                    continue
                
                try:
                    # Get or create source
                    source = source_repo.get_or_create(
                        name=provider_name,
                        provider_type=result.provider_name,
                        base_url="",
                    )
                    
                    # Persist based on provider type
                    if provider_name == "tiingo":
                        inserted, updated = await self._persist_ohlcv(
                            session, result, source.source_id, run_id,
                            instrument_repo, ohlcv_repo
                        )
                    elif provider_name == "fred":
                        inserted, updated = await self._persist_macro(
                            session, result, source.source_id, run_id,
                            macro_series_repo, macro_repo
                        )
                    else:
                        logger.warning(f"Unknown provider type: {provider_name}")
                        continue
                    
                    total_inserted += inserted
                    total_updated += updated
                    
                except Exception as e:
                    logger.error(f"Failed to persist {provider_name} data", error=str(e))
                    errors.append(f"{provider_name}: {str(e)}")
        
        return total_inserted, total_updated, errors
    
    async def _persist_ohlcv(
        self,
        session,
        result: ProviderResult,
        source_id: int,
        run_id: int,
        instrument_repo: InstrumentRepository,
        ohlcv_repo: OHLCVRepository,
    ) -> tuple[int, int]:
        """Persist OHLCV data."""
        df = result.data
        
        # Get or create instruments
        ticker_to_id = {}
        for ticker in df["ticker"].unique():
            instrument = instrument_repo.get_by_ticker(ticker)
            if instrument is None:
                # Create new instrument
                from atlas.storage.models import DimInstrument
                instrument = DimInstrument(
                    ticker=ticker,
                    asset_type="equity",  # Default, will be updated
                    tiingo_ticker=ticker,
                )
                instrument_repo.add(instrument)
            ticker_to_id[ticker] = instrument.instrument_id
        
        # Prepare records
        records = []
        for _, row in df.iterrows():
            records.append({
                "instrument_id": ticker_to_id[row["ticker"]],
                "trade_date": row["trade_date"],
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "close": row.get("close"),
                "volume": row.get("volume"),
                "adj_open": row.get("adj_open"),
                "adj_high": row.get("adj_high"),
                "adj_low": row.get("adj_low"),
                "adj_close": row.get("adj_close"),
                "adj_volume": row.get("adj_volume"),
                "dividend": row.get("dividend"),
                "split_factor": row.get("split_factor"),
            })
        
        return ohlcv_repo.upsert_batch(records, source_id, run_id)
    
    async def _persist_macro(
        self,
        session,
        result: ProviderResult,
        source_id: int,
        run_id: int,
        series_repo: MacroSeriesRepository,
        macro_repo: MacroRepository,
    ) -> tuple[int, int]:
        """Persist macro data."""
        df = result.data
        
        # Get series configuration for category info
        from atlas.providers.fred import FredProvider
        fred = FredProvider()
        all_series = {s["fred_id"]: s for s in fred.get_all_series()}
        
        # Get or create series
        series_to_id = {}
        for fred_id in df["fred_id"].unique():
            series = series_repo.get_by_fred_id(fred_id)
            if series is None:
                # Get series info
                series_info = all_series.get(fred_id, {})
                from atlas.storage.models import DimMacroSeries
                series = DimMacroSeries(
                    fred_id=fred_id,
                    name=series_info.get("name", fred_id),
                    category=series_info.get("category", "unknown"),
                    subcategory=series_info.get("subcategory"),
                    frequency=series_info.get("frequency"),
                )
                series_repo.add(series)
            series_to_id[fred_id] = series.series_id
        
        # Prepare records
        records = []
        for _, row in df.iterrows():
            if row["value"] is not None:
                records.append({
                    "series_id": series_to_id[row["fred_id"]],
                    "obs_date": row["obs_date"],
                    "value": row["value"],
                })
        
        return macro_repo.upsert_batch(records, source_id, run_id)
    
    async def _calculate_features(
        self,
        target_date: date,
        instruments: Optional[list[str]],
        run_id: int,
    ) -> None:
        """Calculate features for the target date."""
        # Feature calculation will be implemented in the feature engine
        logger.info("Feature calculation placeholder - will be implemented")
        pass
    
    def _determine_status(
        self,
        provider_results: dict[str, ProviderResult],
        errors: list[str],
    ) -> RunStatus:
        """Determine the overall run status."""
        if not provider_results:
            return RunStatus.FAILED
        
        all_success = all(r.success for r in provider_results.values())
        any_success = any(r.success or r.partial_failure for r in provider_results.values())
        
        if all_success and not errors:
            return RunStatus.SUCCESS
        elif any_success:
            return RunStatus.PARTIAL
        else:
            return RunStatus.FAILED
