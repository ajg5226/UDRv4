"""SQLAlchemy models for ATLAS database schema."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class DimSource(Base):
    """Data source/provider metadata."""

    __tablename__ = "dim_source"

    source_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    provider_type: Mapped[str] = mapped_column(String(50), nullable=False)
    base_url: Mapped[Optional[str]] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    # Relationships
    ohlcv_records: Mapped[list["FactOHLCV"]] = relationship(back_populates="source")
    macro_records: Mapped[list["FactMacro"]] = relationship(back_populates="source")
    feature_records: Mapped[list["FactFeature"]] = relationship(back_populates="source")

    def __repr__(self) -> str:
        return f"<DimSource(name='{self.name}', type='{self.provider_type}')>"


class DimInstrument(Base):
    """Master list of tradeable instruments."""

    __tablename__ = "dim_instrument"

    instrument_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    exchange: Mapped[Optional[str]] = mapped_column(String(50))
    asset_type: Mapped[str] = mapped_column(String(50), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    sector: Mapped[Optional[str]] = mapped_column(String(100))
    industry: Mapped[Optional[str]] = mapped_column(String(100))
    country: Mapped[Optional[str]] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Provider-specific identifiers
    tiingo_ticker: Mapped[Optional[str]] = mapped_column(String(20))
    
    # Data availability
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    # Relationships
    tags: Mapped[list["InstrumentTag"]] = relationship(
        back_populates="instrument", cascade="all, delete-orphan"
    )
    ohlcv_records: Mapped[list["FactOHLCV"]] = relationship(back_populates="instrument")
    feature_records: Mapped[list["FactFeature"]] = relationship(back_populates="instrument")

    __table_args__ = (
        UniqueConstraint("ticker", "exchange", name="uq_instrument_ticker_exchange"),
        Index("ix_instrument_ticker", "ticker"),
        Index("ix_instrument_asset_type", "asset_type"),
        Index("ix_instrument_is_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<DimInstrument(ticker='{self.ticker}', type='{self.asset_type}')>"


class InstrumentTag(Base):
    """Tags for instruments (portfolios, watchlists, etc.)."""

    __tablename__ = "instrument_tag"

    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dim_instrument.instrument_id"), primary_key=True
    )
    tag: Mapped[str] = mapped_column(String(100), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationships
    instrument: Mapped["DimInstrument"] = relationship(back_populates="tags")

    __table_args__ = (Index("ix_instrument_tag_tag", "tag"),)

    def __repr__(self) -> str:
        return f"<InstrumentTag(instrument_id={self.instrument_id}, tag='{self.tag}')>"


class DimMacroSeries(Base):
    """Macroeconomic series metadata."""

    __tablename__ = "dim_macro_series"

    series_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fred_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # growth, liquidity, risk_appetite
    subcategory: Mapped[Optional[str]] = mapped_column(String(100))
    frequency: Mapped[Optional[str]] = mapped_column(String(20))
    units: Mapped[Optional[str]] = mapped_column(String(100))
    seasonal_adj: Mapped[Optional[str]] = mapped_column(String(50))
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    # Relationships
    macro_records: Mapped[list["FactMacro"]] = relationship(back_populates="series")

    __table_args__ = (
        Index("ix_macro_series_category", "category"),
        Index("ix_macro_series_fred_id", "fred_id"),
    )

    def __repr__(self) -> str:
        return f"<DimMacroSeries(fred_id='{self.fred_id}', category='{self.category}')>"


class FactOHLCV(Base):
    """Daily OHLCV price data."""

    __tablename__ = "fact_ohlcv"

    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dim_instrument.instrument_id"), primary_key=True
    )
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey("dim_source.source_id"))
    
    # Raw prices
    open: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    high: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    low: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    close: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    volume: Mapped[Optional[int]] = mapped_column(BigInteger)
    
    # Adjusted prices
    adj_open: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    adj_high: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    adj_low: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    adj_close: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    adj_volume: Mapped[Optional[int]] = mapped_column(BigInteger)
    
    # Corporate actions
    dividend: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    split_factor: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    
    # Metadata
    run_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("pipeline_run.run_id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationships
    instrument: Mapped["DimInstrument"] = relationship(back_populates="ohlcv_records")
    source: Mapped["DimSource"] = relationship(back_populates="ohlcv_records")
    pipeline_run: Mapped[Optional["PipelineRun"]] = relationship(back_populates="ohlcv_records")

    __table_args__ = (
        Index("ix_ohlcv_trade_date", "trade_date"),
        Index("ix_ohlcv_instrument_date", "instrument_id", "trade_date", postgresql_using="btree"),
    )

    def __repr__(self) -> str:
        return f"<FactOHLCV(instrument_id={self.instrument_id}, date={self.trade_date})>"


class FactMacro(Base):
    """Macroeconomic indicator observations."""

    __tablename__ = "fact_macro"

    series_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dim_macro_series.series_id"), primary_key=True
    )
    obs_date: Mapped[date] = mapped_column(Date, primary_key=True)
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey("dim_source.source_id"))
    value: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    
    # Metadata
    run_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("pipeline_run.run_id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationships
    series: Mapped["DimMacroSeries"] = relationship(back_populates="macro_records")
    source: Mapped["DimSource"] = relationship(back_populates="macro_records")
    pipeline_run: Mapped[Optional["PipelineRun"]] = relationship(back_populates="macro_records")

    __table_args__ = (
        Index("ix_macro_obs_date", "obs_date"),
        Index("ix_macro_series_date", "series_id", "obs_date", postgresql_using="btree"),
    )

    def __repr__(self) -> str:
        return f"<FactMacro(series_id={self.series_id}, date={self.obs_date})>"


class FactFeature(Base):
    """Engineered features derived from price/macro data."""

    __tablename__ = "fact_feature"

    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dim_instrument.instrument_id"), primary_key=True
    )
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    feature_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    source_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("dim_source.source_id"))
    value: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    
    # Versioning and lineage (added for production alpha)
    feature_version: Mapped[Optional[str]] = mapped_column(String(20))
    params_hash: Mapped[Optional[str]] = mapped_column(String(64))
    transform_type: Mapped[Optional[str]] = mapped_column(String(20))  # raw, rank, zscore
    input_vintage: Mapped[Optional[datetime]] = mapped_column(DateTime)
    calc_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Metadata
    run_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("pipeline_run.run_id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationships
    instrument: Mapped["DimInstrument"] = relationship(back_populates="feature_records")
    source: Mapped[Optional["DimSource"]] = relationship(back_populates="feature_records")
    pipeline_run: Mapped[Optional["PipelineRun"]] = relationship(back_populates="feature_records")

    __table_args__ = (
        Index("ix_feature_trade_date", "trade_date"),
        Index("ix_feature_name_date", "feature_name", "trade_date"),
        Index("ix_feature_instrument_name_date", "instrument_id", "feature_name", "trade_date"),
        Index("ix_feature_version", "feature_name", "feature_version"),
    )

    def __repr__(self) -> str:
        return f"<FactFeature(instrument={self.instrument_id}, feature='{self.feature_name}', date={self.trade_date})>"


class FeatureDiagnosticRecord(Base):
    """Feature diagnostics (IC, hit rate, stability) for signal quality tracking."""

    __tablename__ = "feature_diagnostic"

    diagnostic_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    feature_name: Mapped[str] = mapped_column(String(100), nullable=False)
    feature_version: Mapped[Optional[str]] = mapped_column(String(20))
    universe_scope: Mapped[str] = mapped_column(String(50), default="all")
    calc_date: Mapped[date] = mapped_column(Date, nullable=False)
    forward_horizon: Mapped[int] = mapped_column(Integer, nullable=False)  # 5, 21, 63, 126
    
    # Core metrics
    ic_spearman: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))
    ic_pearson: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))
    hit_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))
    t_stat: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))
    n_observations: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Regime conditioning
    regime: Mapped[Optional[str]] = mapped_column(String(20), default="all")
    
    # Metadata
    run_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("pipeline_run.run_id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_diagnostic_feature_date", "feature_name", "calc_date"),
        Index("ix_diagnostic_horizon", "forward_horizon"),
        Index("ix_diagnostic_regime", "regime"),
    )

    def __repr__(self) -> str:
        return f"<FeatureDiagnostic(feature='{self.feature_name}', date={self.calc_date}, horizon={self.forward_horizon})>"


class PipelineRun(Base):
    """Pipeline execution metadata."""

    __tablename__ = "pipeline_run"

    run_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_type: Mapped[str] = mapped_column(String(50), nullable=False)  # nightly, backfill, manual
    run_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # running, success, partial, failed
    
    # Execution details
    providers_run: Mapped[Optional[str]] = mapped_column(String(500))  # JSON array
    records_inserted: Mapped[Optional[int]] = mapped_column(Integer)
    records_updated: Mapped[Optional[int]] = mapped_column(Integer)
    errors: Mapped[Optional[str]] = mapped_column(Text)
    tags_filter: Mapped[Optional[str]] = mapped_column(String(500))  # JSON array
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationships
    ohlcv_records: Mapped[list["FactOHLCV"]] = relationship(back_populates="pipeline_run")
    macro_records: Mapped[list["FactMacro"]] = relationship(back_populates="pipeline_run")
    feature_records: Mapped[list["FactFeature"]] = relationship(back_populates="pipeline_run")

    __table_args__ = (
        Index("ix_pipeline_run_date", "run_date"),
        Index("ix_pipeline_run_status", "status"),
        Index("ix_pipeline_run_type_date", "run_type", "run_date"),
    )

    def __repr__(self) -> str:
        return f"<PipelineRun(id={self.run_id}, type='{self.run_type}', status='{self.status}')>"
