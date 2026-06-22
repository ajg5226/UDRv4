"""Repository pattern implementations for database operations."""

import json
from datetime import date, datetime
from typing import Generic, Optional, Type, TypeVar

import pandas as pd
from sqlalchemy import and_, delete, select, update
from sqlalchemy.orm import Session

from atlas.core.logging import get_logger
from atlas.storage.models import (
    Base,
    DimInstrument,
    DimMacroSeries,
    DimSource,
    FactFeature,
    FactMacro,
    FactOHLCV,
    InstrumentTag,
    PipelineRun,
)

logger = get_logger(__name__)

T = TypeVar("T", bound=Base)


def _is_missing_value(value: object) -> bool:
    """Return True for None/NaN-like scalar values without treating zero as missing."""
    if value is None:
        return True

    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False

    try:
        return bool(missing)
    except (TypeError, ValueError):
        return False


def _float_or_none(value: object) -> Optional[float]:
    """Convert a stored numeric value to float while preserving legitimate zeroes."""
    if _is_missing_value(value):
        return None
    return float(value)


class BaseRepository(Generic[T]):
    """Base repository with common CRUD operations."""

    model: Type[T]

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, id_value: int) -> Optional[T]:
        """Get a record by primary key."""
        return self.session.get(self.model, id_value)

    def get_all(self) -> list[T]:
        """Get all records."""
        return list(self.session.scalars(select(self.model)))

    def add(self, entity: T) -> T:
        """Add a new record."""
        self.session.add(entity)
        self.session.flush()
        return entity

    def add_all(self, entities: list[T]) -> list[T]:
        """Add multiple records."""
        self.session.add_all(entities)
        self.session.flush()
        return entities

    def delete(self, entity: T) -> None:
        """Delete a record."""
        self.session.delete(entity)
        self.session.flush()


class SourceRepository(BaseRepository[DimSource]):
    """Repository for data source operations."""

    model = DimSource

    def get_by_name(self, name: str) -> Optional[DimSource]:
        """Get source by name."""
        stmt = select(DimSource).where(DimSource.name == name)
        return self.session.scalar(stmt)

    def get_active(self) -> list[DimSource]:
        """Get all active sources."""
        stmt = select(DimSource).where(DimSource.is_active == True)
        return list(self.session.scalars(stmt))

    def get_or_create(self, name: str, provider_type: str, base_url: str = "") -> DimSource:
        """Get existing source or create new one."""
        source = self.get_by_name(name)
        if source is None:
            source = DimSource(
                name=name,
                provider_type=provider_type,
                base_url=base_url,
            )
            self.add(source)
        return source


class InstrumentRepository(BaseRepository[DimInstrument]):
    """Repository for instrument operations."""

    model = DimInstrument

    def get_by_ticker(self, ticker: str, exchange: Optional[str] = None) -> Optional[DimInstrument]:
        """Get instrument by ticker (and optionally exchange)."""
        stmt = select(DimInstrument).where(DimInstrument.ticker == ticker)
        if exchange:
            stmt = stmt.where(DimInstrument.exchange == exchange)
        return self.session.scalar(stmt)

    def get_by_tickers(self, tickers: list[str]) -> list[DimInstrument]:
        """Get instruments by list of tickers."""
        stmt = select(DimInstrument).where(DimInstrument.ticker.in_(tickers))
        return list(self.session.scalars(stmt))

    def get_active(self) -> list[DimInstrument]:
        """Get all active instruments."""
        stmt = select(DimInstrument).where(DimInstrument.is_active == True)
        return list(self.session.scalars(stmt))

    def get_by_tags(self, tags: list[str]) -> list[DimInstrument]:
        """Get instruments that have any of the specified tags."""
        stmt = (
            select(DimInstrument)
            .join(InstrumentTag)
            .where(InstrumentTag.tag.in_(tags))
            .distinct()
        )
        return list(self.session.scalars(stmt))

    def get_by_asset_type(self, asset_type: str) -> list[DimInstrument]:
        """Get instruments by asset type."""
        stmt = select(DimInstrument).where(
            and_(DimInstrument.asset_type == asset_type, DimInstrument.is_active == True)
        )
        return list(self.session.scalars(stmt))

    def upsert_from_dataframe(self, df: pd.DataFrame) -> int:
        """
        Upsert instruments from a DataFrame.
        
        Expected columns: ticker, name, exchange, asset_type, currency, sector, industry
        
        Returns count of records processed.
        """
        if df.empty:
            return 0

        records = df.to_dict("records")
        count = 0

        for record in records:
            existing = self.get_by_ticker(record["ticker"], record.get("exchange"))
            if existing:
                # Update
                for key, value in record.items():
                    if hasattr(existing, key) and value is not None:
                        setattr(existing, key, value)
                existing.updated_at = datetime.utcnow()
            else:
                # Insert
                instrument = DimInstrument(**record)
                self.add(instrument)
            count += 1

        return count

    def add_tag(self, instrument_id: int, tag: str) -> None:
        """Add a tag to an instrument."""
        existing = self.session.scalar(
            select(InstrumentTag).where(
                and_(
                    InstrumentTag.instrument_id == instrument_id,
                    InstrumentTag.tag == tag,
                )
            )
        )
        if not existing:
            self.session.add(InstrumentTag(instrument_id=instrument_id, tag=tag))
            self.session.flush()

    def remove_tag(self, instrument_id: int, tag: str) -> None:
        """Remove a tag from an instrument."""
        stmt = delete(InstrumentTag).where(
            and_(
                InstrumentTag.instrument_id == instrument_id,
                InstrumentTag.tag == tag,
            )
        )
        self.session.execute(stmt)
        self.session.flush()

    def get_tags(self, instrument_id: int) -> list[str]:
        """Get all tags for an instrument."""
        stmt = select(InstrumentTag.tag).where(InstrumentTag.instrument_id == instrument_id)
        return list(self.session.scalars(stmt))


class MacroSeriesRepository(BaseRepository[DimMacroSeries]):
    """Repository for macro series operations."""

    model = DimMacroSeries

    def get_by_fred_id(self, fred_id: str) -> Optional[DimMacroSeries]:
        """Get series by FRED ID."""
        stmt = select(DimMacroSeries).where(DimMacroSeries.fred_id == fred_id)
        return self.session.scalar(stmt)

    def get_by_category(self, category: str) -> list[DimMacroSeries]:
        """Get series by category."""
        stmt = select(DimMacroSeries).where(
            and_(DimMacroSeries.category == category, DimMacroSeries.is_active == True)
        )
        return list(self.session.scalars(stmt))

    def get_active(self) -> list[DimMacroSeries]:
        """Get all active series."""
        stmt = select(DimMacroSeries).where(DimMacroSeries.is_active == True)
        return list(self.session.scalars(stmt))

    def get_or_create(
        self,
        fred_id: str,
        name: str,
        category: str,
        **kwargs,
    ) -> DimMacroSeries:
        """Get existing series or create new one."""
        series = self.get_by_fred_id(fred_id)
        if series is None:
            series = DimMacroSeries(
                fred_id=fred_id,
                name=name,
                category=category,
                **kwargs,
            )
            self.add(series)
        return series


class OHLCVRepository(BaseRepository[FactOHLCV]):
    """Repository for OHLCV price data operations."""

    model = FactOHLCV

    def get_by_instrument_date(
        self,
        instrument_id: int,
        trade_date: date,
    ) -> Optional[FactOHLCV]:
        """Get OHLCV record for instrument and date."""
        stmt = select(FactOHLCV).where(
            and_(
                FactOHLCV.instrument_id == instrument_id,
                FactOHLCV.trade_date == trade_date,
            )
        )
        return self.session.scalar(stmt)

    def get_range(
        self,
        instrument_id: int,
        start_date: date,
        end_date: date,
    ) -> list[FactOHLCV]:
        """Get OHLCV records for date range."""
        stmt = (
            select(FactOHLCV)
            .where(
                and_(
                    FactOHLCV.instrument_id == instrument_id,
                    FactOHLCV.trade_date >= start_date,
                    FactOHLCV.trade_date <= end_date,
                )
            )
            .order_by(FactOHLCV.trade_date)
        )
        return list(self.session.scalars(stmt))

    def get_latest(self, instrument_id: int) -> Optional[FactOHLCV]:
        """Get most recent OHLCV record for instrument."""
        stmt = (
            select(FactOHLCV)
            .where(FactOHLCV.instrument_id == instrument_id)
            .order_by(FactOHLCV.trade_date.desc())
            .limit(1)
        )
        return self.session.scalar(stmt)

    def get_as_dataframe(
        self,
        instrument_ids: Optional[list[int]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pd.DataFrame:
        """Get OHLCV data as a DataFrame."""
        stmt = select(FactOHLCV)
        
        conditions = []
        if instrument_ids:
            conditions.append(FactOHLCV.instrument_id.in_(instrument_ids))
        if start_date:
            conditions.append(FactOHLCV.trade_date >= start_date)
        if end_date:
            conditions.append(FactOHLCV.trade_date <= end_date)
        
        if conditions:
            stmt = stmt.where(and_(*conditions))
        
        stmt = stmt.order_by(FactOHLCV.instrument_id, FactOHLCV.trade_date)
        
        results = self.session.execute(stmt)
        records = [
            {
                "instrument_id": r.instrument_id,
                "trade_date": r.trade_date,
                "open": _float_or_none(r.open),
                "high": _float_or_none(r.high),
                "low": _float_or_none(r.low),
                "close": _float_or_none(r.close),
                "volume": r.volume,
                "adj_open": _float_or_none(r.adj_open),
                "adj_high": _float_or_none(r.adj_high),
                "adj_low": _float_or_none(r.adj_low),
                "adj_close": _float_or_none(r.adj_close),
                "adj_volume": r.adj_volume,
            }
            for r in results.scalars()
        ]
        return pd.DataFrame(records)

    def upsert_batch(
        self,
        records: list[dict],
        source_id: int,
        run_id: Optional[int] = None,
    ) -> tuple[int, int]:
        """
        Upsert a batch of OHLCV records.
        
        Returns (inserted_count, updated_count).
        """
        if not records:
            return 0, 0

        inserted = 0
        updated = 0

        for record in records:
            record["source_id"] = source_id
            if run_id:
                record["run_id"] = run_id

            existing = self.get_by_instrument_date(
                record["instrument_id"],
                record["trade_date"],
            )

            if existing:
                # Update
                for key, value in record.items():
                    if hasattr(existing, key) and not _is_missing_value(value):
                        setattr(existing, key, value)
                updated += 1
            else:
                # Insert
                clean_record = {
                    key: None if _is_missing_value(value) else value
                    for key, value in record.items()
                }
                self.session.add(FactOHLCV(**clean_record))
                inserted += 1

        self.session.flush()
        return inserted, updated


class MacroRepository(BaseRepository[FactMacro]):
    """Repository for macro data operations."""

    model = FactMacro

    def get_by_series_date(
        self,
        series_id: int,
        obs_date: date,
    ) -> Optional[FactMacro]:
        """Get macro record for series and date."""
        stmt = select(FactMacro).where(
            and_(
                FactMacro.series_id == series_id,
                FactMacro.obs_date == obs_date,
            )
        )
        return self.session.scalar(stmt)

    def get_range(
        self,
        series_id: int,
        start_date: date,
        end_date: date,
    ) -> list[FactMacro]:
        """Get macro records for date range."""
        stmt = (
            select(FactMacro)
            .where(
                and_(
                    FactMacro.series_id == series_id,
                    FactMacro.obs_date >= start_date,
                    FactMacro.obs_date <= end_date,
                )
            )
            .order_by(FactMacro.obs_date)
        )
        return list(self.session.scalars(stmt))

    def get_as_dataframe(
        self,
        series_ids: Optional[list[int]] = None,
        category: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pd.DataFrame:
        """Get macro data as a DataFrame."""
        stmt = select(FactMacro).join(DimMacroSeries)
        
        conditions = []
        if series_ids:
            conditions.append(FactMacro.series_id.in_(series_ids))
        if category:
            conditions.append(DimMacroSeries.category == category)
        if start_date:
            conditions.append(FactMacro.obs_date >= start_date)
        if end_date:
            conditions.append(FactMacro.obs_date <= end_date)
        
        if conditions:
            stmt = stmt.where(and_(*conditions))
        
        results = self.session.execute(stmt)
        records = [
            {
                "series_id": r.series_id,
                "obs_date": r.obs_date,
                "value": _float_or_none(r.value),
            }
            for r in results.scalars()
        ]
        return pd.DataFrame(records)

    def upsert_batch(
        self,
        records: list[dict],
        source_id: int,
        run_id: Optional[int] = None,
    ) -> tuple[int, int]:
        """Upsert a batch of macro records."""
        if not records:
            return 0, 0

        inserted = 0
        updated = 0

        for record in records:
            record["source_id"] = source_id
            if run_id:
                record["run_id"] = run_id

            existing = self.get_by_series_date(record["series_id"], record["obs_date"])

            if existing:
                existing.value = record["value"]
                updated += 1
            else:
                self.session.add(FactMacro(**record))
                inserted += 1

        self.session.flush()
        return inserted, updated


class FeatureRepository(BaseRepository[FactFeature]):
    """Repository for feature data operations."""

    model = FactFeature

    def get_by_key(
        self,
        instrument_id: int,
        trade_date: date,
        feature_name: str,
    ) -> Optional[FactFeature]:
        """Get feature record by composite key."""
        stmt = select(FactFeature).where(
            and_(
                FactFeature.instrument_id == instrument_id,
                FactFeature.trade_date == trade_date,
                FactFeature.feature_name == feature_name,
            )
        )
        return self.session.scalar(stmt)

    def get_features_for_date(
        self,
        trade_date: date,
        feature_names: Optional[list[str]] = None,
        instrument_ids: Optional[list[int]] = None,
    ) -> pd.DataFrame:
        """Get all features for a date as a DataFrame (pivoted by feature name)."""
        stmt = select(FactFeature).where(FactFeature.trade_date == trade_date)
        
        if feature_names:
            stmt = stmt.where(FactFeature.feature_name.in_(feature_names))
        if instrument_ids:
            stmt = stmt.where(FactFeature.instrument_id.in_(instrument_ids))
        
        results = list(self.session.scalars(stmt))
        
        if not results:
            return pd.DataFrame()
        
        records = [
            {
                "instrument_id": r.instrument_id,
                "trade_date": r.trade_date,
                "feature_name": r.feature_name,
                "value": _float_or_none(r.value),
            }
            for r in results
        ]
        df = pd.DataFrame(records)
        
        # Pivot to wide format
        if not df.empty:
            df = df.pivot(
                index=["instrument_id", "trade_date"],
                columns="feature_name",
                values="value",
            ).reset_index()
        
        return df

    def upsert_batch(
        self,
        records: list[dict],
        run_id: Optional[int] = None,
    ) -> tuple[int, int]:
        """Upsert a batch of feature records."""
        if not records:
            return 0, 0

        inserted = 0
        updated = 0

        for record in records:
            if run_id:
                record["run_id"] = run_id

            existing = self.get_by_key(
                record["instrument_id"],
                record["trade_date"],
                record["feature_name"],
            )

            if existing:
                for key, value in record.items():
                    if hasattr(existing, key):
                        setattr(existing, key, value)
                updated += 1
            else:
                self.session.add(FactFeature(**record))
                inserted += 1

        self.session.flush()
        return inserted, updated


class PipelineRunRepository(BaseRepository[PipelineRun]):
    """Repository for pipeline run metadata."""

    model = PipelineRun

    def create_run(
        self,
        run_type: str,
        run_date: date,
        providers: Optional[list[str]] = None,
        tags_filter: Optional[list[str]] = None,
    ) -> PipelineRun:
        """Create a new pipeline run record."""
        run = PipelineRun(
            run_type=run_type,
            run_date=run_date,
            start_time=datetime.utcnow(),
            status="running",
            providers_run=json.dumps(providers) if providers else None,
            tags_filter=json.dumps(tags_filter) if tags_filter else None,
        )
        self.add(run)
        return run

    def complete_run(
        self,
        run_id: int,
        status: str,
        records_inserted: int = 0,
        records_updated: int = 0,
        errors: Optional[str] = None,
    ) -> None:
        """Mark a run as complete."""
        stmt = (
            update(PipelineRun)
            .where(PipelineRun.run_id == run_id)
            .values(
                end_time=datetime.utcnow(),
                status=status,
                records_inserted=records_inserted,
                records_updated=records_updated,
                errors=errors,
            )
        )
        self.session.execute(stmt)
        self.session.flush()

    def get_latest_run(self, run_type: Optional[str] = None) -> Optional[PipelineRun]:
        """Get the most recent pipeline run."""
        stmt = select(PipelineRun).order_by(PipelineRun.start_time.desc())
        if run_type:
            stmt = stmt.where(PipelineRun.run_type == run_type)
        return self.session.scalar(stmt.limit(1))

    def get_runs_for_date(self, run_date: date) -> list[PipelineRun]:
        """Get all runs for a specific date."""
        stmt = (
            select(PipelineRun)
            .where(PipelineRun.run_date == run_date)
            .order_by(PipelineRun.start_time.desc())
        )
        return list(self.session.scalars(stmt))

    def get_failed_runs(self, since: Optional[datetime] = None) -> list[PipelineRun]:
        """Get failed runs, optionally since a specific time."""
        stmt = select(PipelineRun).where(PipelineRun.status == "failed")
        if since:
            stmt = stmt.where(PipelineRun.start_time >= since)
        return list(self.session.scalars(stmt.order_by(PipelineRun.start_time.desc())))
