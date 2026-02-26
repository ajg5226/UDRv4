"""Backfill management for historical data loading."""

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from atlas.core.config import get_settings
from atlas.core.logging import get_logger, bind_context, clear_context
from atlas.pipeline.orchestrator import (
    PipelineOrchestrator,
    RunConfig,
    RunResult,
    RunType,
    RunStatus,
)

logger = get_logger(__name__)


@dataclass
class BackfillConfig:
    """Configuration for a backfill operation."""
    
    start_date: date
    end_date: date
    providers: Optional[list[str]] = None
    instruments: Optional[list[str]] = None
    tags: Optional[list[str]] = None
    
    # Batch settings
    batch_size_days: int = 30
    parallel_batches: int = 1  # Number of date batches to run in parallel
    
    # Control settings
    skip_weekends: bool = True
    skip_holidays: bool = False  # Would need holiday calendar
    skip_features: bool = False
    continue_on_error: bool = True
    
    # Resume support
    resume_from: Optional[date] = None
    
    def __post_init__(self) -> None:
        if self.start_date > self.end_date:
            raise ValueError("start_date must be before or equal to end_date")
        
        if self.resume_from and (self.resume_from < self.start_date or self.resume_from > self.end_date):
            raise ValueError("resume_from must be within the date range")


@dataclass
class BackfillResult:
    """Result of a backfill operation."""
    
    start_date: date
    end_date: date
    start_time: datetime
    end_time: datetime
    
    # Results per date
    run_results: dict[date, RunResult] = field(default_factory=dict)
    
    # Aggregates
    total_dates_processed: int = 0
    successful_dates: int = 0
    failed_dates: int = 0
    skipped_dates: int = 0
    
    total_records_inserted: int = 0
    total_records_updated: int = 0
    
    # Errors
    errors: dict[date, list[str]] = field(default_factory=dict)
    
    @property
    def duration_seconds(self) -> float:
        """Get total duration in seconds."""
        return (self.end_time - self.start_time).total_seconds()
    
    @property
    def success_rate(self) -> float:
        """Get success rate as a percentage."""
        if self.total_dates_processed == 0:
            return 0.0
        return (self.successful_dates / self.total_dates_processed) * 100
    
    @property
    def is_complete(self) -> bool:
        """Check if backfill was fully successful."""
        return self.failed_dates == 0


class BackfillManager:
    """
    Manages backfill operations for historical data loading.
    
    Features:
    - Batch processing by date range
    - Resume support
    - Parallel execution (optional)
    - Progress tracking
    - Error handling with continue option
    """
    
    def __init__(self, orchestrator: Optional[PipelineOrchestrator] = None) -> None:
        self._orchestrator = orchestrator or PipelineOrchestrator()
        self._settings = get_settings()
    
    async def run(self, config: BackfillConfig) -> BackfillResult:
        """
        Execute a backfill operation.
        
        Args:
            config: Backfill configuration
            
        Returns:
            BackfillResult with details of the operation
        """
        start_time = datetime.utcnow()
        
        bind_context(
            operation="backfill",
            start_date=str(config.start_date),
            end_date=str(config.end_date),
        )
        
        logger.info(
            "Starting backfill",
            providers=config.providers,
            batch_size=config.batch_size_days,
        )
        
        # Initialize orchestrator
        await self._orchestrator.initialize()
        
        # Generate date list
        dates = self._generate_dates(config)
        
        logger.info(f"Backfill will process {len(dates)} dates")
        
        result = BackfillResult(
            start_date=config.start_date,
            end_date=config.end_date,
            start_time=start_time,
            end_time=start_time,  # Will be updated
        )
        
        try:
            # Process dates in batches
            batches = self._create_batches(dates, config.batch_size_days)
            
            for batch_idx, batch_dates in enumerate(batches):
                logger.info(
                    f"Processing batch {batch_idx + 1}/{len(batches)}",
                    dates=f"{batch_dates[0]} to {batch_dates[-1]}",
                    count=len(batch_dates),
                )
                
                if config.parallel_batches > 1:
                    batch_results = await self._process_dates_parallel(
                        batch_dates, config, config.parallel_batches
                    )
                else:
                    batch_results = await self._process_dates_sequential(
                        batch_dates, config
                    )
                
                # Aggregate results
                for run_date, run_result in batch_results.items():
                    result.run_results[run_date] = run_result
                    result.total_dates_processed += 1
                    
                    if run_result.status == RunStatus.SUCCESS:
                        result.successful_dates += 1
                    elif run_result.status == RunStatus.PARTIAL:
                        result.successful_dates += 1  # Count partial as success
                        if run_result.errors:
                            result.errors[run_date] = run_result.errors
                    else:
                        result.failed_dates += 1
                        if run_result.errors:
                            result.errors[run_date] = run_result.errors
                    
                    result.total_records_inserted += run_result.records_inserted
                    result.total_records_updated += run_result.records_updated
                
                # Log progress
                progress = (batch_idx + 1) / len(batches) * 100
                logger.info(
                    f"Backfill progress: {progress:.1f}%",
                    successful=result.successful_dates,
                    failed=result.failed_dates,
                )
        
        except Exception as e:
            logger.error("Backfill failed", error=str(e))
            raise
        
        finally:
            result.end_time = datetime.utcnow()
            clear_context()
        
        logger.info(
            "Backfill complete",
            total_dates=result.total_dates_processed,
            successful=result.successful_dates,
            failed=result.failed_dates,
            duration_seconds=result.duration_seconds,
            records_inserted=result.total_records_inserted,
            records_updated=result.total_records_updated,
        )
        
        return result
    
    def _generate_dates(self, config: BackfillConfig) -> list[date]:
        """Generate list of dates to process."""
        dates = []
        current = config.resume_from or config.start_date
        
        while current <= config.end_date:
            # Skip weekends if configured
            if config.skip_weekends and current.weekday() >= 5:
                current += timedelta(days=1)
                continue
            
            dates.append(current)
            current += timedelta(days=1)
        
        return dates
    
    def _create_batches(self, dates: list[date], batch_size: int) -> list[list[date]]:
        """Split dates into batches."""
        return [dates[i:i + batch_size] for i in range(0, len(dates), batch_size)]
    
    async def _process_dates_sequential(
        self,
        dates: list[date],
        config: BackfillConfig,
    ) -> dict[date, RunResult]:
        """Process dates sequentially."""
        results = {}
        
        for run_date in dates:
            try:
                run_config = RunConfig(
                    run_type=RunType.BACKFILL,
                    target_date=run_date,
                    providers=config.providers,
                    instruments=config.instruments,
                    tags=config.tags,
                    skip_features=config.skip_features,
                )
                
                result = await self._orchestrator.run(run_config)
                results[run_date] = result
                
            except Exception as e:
                logger.error(f"Failed to process date {run_date}", error=str(e))
                
                if not config.continue_on_error:
                    raise
                
                # Create a failed result
                results[run_date] = RunResult(
                    run_id=0,
                    status=RunStatus.FAILED,
                    run_date=run_date,
                    start_time=datetime.utcnow(),
                    end_time=datetime.utcnow(),
                    errors=[str(e)],
                )
        
        return results
    
    async def _process_dates_parallel(
        self,
        dates: list[date],
        config: BackfillConfig,
        max_parallel: int,
    ) -> dict[date, RunResult]:
        """Process dates in parallel with concurrency limit."""
        results = {}
        semaphore = asyncio.Semaphore(max_parallel)
        
        async def process_with_semaphore(run_date: date) -> tuple[date, RunResult]:
            async with semaphore:
                try:
                    run_config = RunConfig(
                        run_type=RunType.BACKFILL,
                        target_date=run_date,
                        providers=config.providers,
                        instruments=config.instruments,
                        tags=config.tags,
                        skip_features=config.skip_features,
                    )
                    
                    result = await self._orchestrator.run(run_config)
                    return run_date, result
                    
                except Exception as e:
                    logger.error(f"Failed to process date {run_date}", error=str(e))
                    
                    return run_date, RunResult(
                        run_id=0,
                        status=RunStatus.FAILED,
                        run_date=run_date,
                        start_time=datetime.utcnow(),
                        end_time=datetime.utcnow(),
                        errors=[str(e)],
                    )
        
        tasks = [process_with_semaphore(d) for d in dates]
        completed = await asyncio.gather(*tasks)
        
        for run_date, result in completed:
            results[run_date] = result
        
        return results
    
    async def estimate_duration(self, config: BackfillConfig) -> dict:
        """
        Estimate the duration of a backfill operation.
        
        Returns dict with estimates.
        """
        dates = self._generate_dates(config)
        num_dates = len(dates)
        
        # Rough estimates based on typical performance
        avg_seconds_per_date = 5  # Conservative estimate
        
        if config.parallel_batches > 1:
            effective_parallelism = min(config.parallel_batches, num_dates)
            estimated_seconds = (num_dates / effective_parallelism) * avg_seconds_per_date
        else:
            estimated_seconds = num_dates * avg_seconds_per_date
        
        return {
            "total_dates": num_dates,
            "batches": len(self._create_batches(dates, config.batch_size_days)),
            "estimated_seconds": estimated_seconds,
            "estimated_minutes": estimated_seconds / 60,
            "estimated_hours": estimated_seconds / 3600,
        }
