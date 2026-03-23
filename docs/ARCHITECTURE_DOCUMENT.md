# ATLAS V1 - System Architecture Document

## Document Information
| Field | Value |
|-------|-------|
| Version | 1.0.1 |
| Last Updated | 2026-03-23 |
| Status | Partially Implemented (Living Document) |

---

## 1. Executive Summary

ATLAS V1 is a **cloud-native nightly data pipeline** designed for institutional investment management. The system automates collection of market data (equities, ETFs, and other exchange-traded instruments) and macroeconomic indicators, transforms and validates the data, stores it in a centralized database, and exposes it through a web dashboard for analysis.

### Key Capabilities
- **Multi-provider data ingestion** with modular architecture
- **Historical backfill** support for any date range
- **Feature engineering framework** for derived analytics
- **Portfolio tagging** to track instrument subsets
- **Macro indicator categorization** (Growth, Liquidity, Risk Appetite)
- **Streamlit dashboard** with role-based access
- **Cloud-agnostic design** with Azure as primary deployment target

### 1.1 Implementation Snapshot (Verified Against Source)

| Area | Current State | Primary Codepaths |
|------|---------------|-------------------|
| Provider ingestion | Implemented for Tiingo + FRED in orchestrator/backfill | `src/atlas/pipeline/orchestrator.py`, `src/atlas/pipeline/backfill.py`, `src/atlas/providers/*.py` |
| Persistence & run metadata | Implemented (`dim_*`, `fact_*`, `pipeline_run`) | `src/atlas/storage/models.py`, `src/atlas/storage/repository.py` |
| Feature execution in pipeline | Placeholder in orchestrator (feature modules exist but are not invoked by nightly/manual flow) | `src/atlas/pipeline/orchestrator.py::_calculate_features`, `src/atlas/features/*` |
| Raw archive to blob | Configured in settings, not wired in orchestrator codepath | `config/default.yaml`, `src/atlas/pipeline/orchestrator.py` |
| Notifications | Configured in settings, no active dispatch in pipeline codepath | `config/default.yaml`, `src/atlas/pipeline/orchestrator.py` |
| CLI instrument sync | Listed in help text but not implemented handler | `src/atlas/cli/main.py` |
| Schema migrations | Schema creation uses SQLAlchemy metadata (`init-db`), no Alembic migration tree in repo | `src/atlas/storage/database.py`, `src/atlas/cli/main.py` |

---

## 2. System Architecture

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              EXTERNAL DATA SOURCES                          │
├─────────────────┬─────────────────┬─────────────────┬──────────────────────┤
│     Tiingo      │  EODHistorical  │     Polygon     │        FRED          │
│   (Primary)     │    (Future)     │    (Future)     │   (Macro Data)       │
└────────┬────────┴────────┬────────┴────────┬────────┴──────────┬───────────┘
         │                 │                 │                   │
         └─────────────────┴─────────────────┴───────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           INGESTION LAYER                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    Provider Registry                                 │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │   │
│  │  │ BaseProvider │  │ BaseProvider │  │ BaseProvider │               │   │
│  │  │   (Tiingo)   │  │   (FRED)     │  │  (Future)    │               │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          PROCESSING LAYER                                   │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐                │
│  │  Validation    │  │ Transformation │  │    Feature     │                │
│  │    Engine      │──│     Engine     │──│    Engine      │                │
│  └────────────────┘  └────────────────┘  └────────────────┘                │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           STORAGE LAYER                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     Azure SQL Database                               │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │   │
│  │  │dim_source│ │dim_instr │ │fact_ohlcv│ │fact_macro│ │fact_feat │  │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘  │   │
│  │  ┌──────────────────────────────────────────────────────────────┐  │   │
│  │  │                    pipeline_run                               │  │   │
│  │  └──────────────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              Azure Blob Storage (Raw Archive)                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PRESENTATION LAYER                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              Streamlit Dashboard (Azure Container Apps)              │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │  Auth    │ │  Prices  │ │  Macro   │ │ Features │               │   │
│  │  │  Module  │ │  View    │ │  View    │ │   View   │               │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        ORCHESTRATION LAYER                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    Azure Functions (Timer Trigger)                   │   │
│  │  ┌──────────────────────────────────────────────────────────────┐  │   │
│  │  │  Pipeline Orchestrator                                        │  │   │
│  │  │  - Nightly scheduled run (configurable)                       │  │   │
│  │  │  - Manual trigger support                                     │  │   │
│  │  │  - Backfill mode                                              │  │   │
│  │  └──────────────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         OPERATIONS LAYER                                    │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐         │
│  │  Azure Key Vault │  │ Application      │  │  Azure Monitor   │         │
│  │  (Secrets)       │  │ Insights (Logs)  │  │  (Alerts)        │         │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘         │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Component Responsibilities

| Component | Responsibility | Azure Service |
|-----------|---------------|---------------|
| **Provider Registry** | Manages data source adapters | Azure Functions |
| **Validation Engine** | Schema & quality checks | Azure Functions |
| **Transformation Engine** | Data normalization | Azure Functions |
| **Feature Engine** | Derived metric calculation | Azure Functions |
| **Primary Storage** | Relational data store | Azure SQL Database |
| **Raw Archive** | Planned source data preservation path (configured, not active in orchestrator) | Azure Blob Storage |
| **Dashboard** | User interface | Azure Container Apps |
| **Orchestrator** | Pipeline scheduling | Azure Functions Timer |
| **Secrets Management** | Credentials storage | Azure Key Vault |
| **Monitoring** | Logs and metrics | Application Insights |

---

## 3. Data Model

### 3.1 Entity Relationship Diagram

```
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│   dim_source    │       │ dim_instrument  │       │ dim_macro_series│
├─────────────────┤       ├─────────────────┤       ├─────────────────┤
│ PK source_id    │       │ PK instrument_id│       │ PK series_id    │
│    name         │       │    ticker       │       │    fred_id      │
│    provider_type│       │    name         │       │    name         │
│    base_url     │       │    exchange     │       │    category     │
│    is_active    │       │    asset_type   │       │    frequency    │
│    created_at   │       │    currency     │       │    units        │
│    updated_at   │       │    is_active    │       │    description  │
└────────┬────────┘       │    created_at   │       │    is_active    │
         │                │    updated_at   │       │    created_at   │
         │                └────────┬────────┘       └────────┬────────┘
         │                         │                         │
         │                         │                         │
         │    ┌────────────────────┼────────────────────┐    │
         │    │                    │                    │    │
         ▼    ▼                    ▼                    ▼    ▼
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│   fact_ohlcv    │       │   fact_feature  │       │   fact_macro    │
├─────────────────┤       ├─────────────────┤       ├─────────────────┤
│ PK,FK instrument│       │ PK,FK instrument│       │ PK,FK series_id │
│ PK    trade_date│       │ PK    trade_date│       │ PK    obs_date  │
│ FK    source_id │       │ PK    feature   │       │ FK    source_id │
│    open         │       │ FK    source_id │       │    value        │
│    high         │       │    value        │       │    run_id       │
│    low          │       │    run_id       │       │    created_at   │
│    close        │       │    created_at   │       └─────────────────┘
│    volume       │       └─────────────────┘
│    adj_open     │
│    adj_high     │       ┌─────────────────┐
│    adj_low      │       │instrument_tag   │
│    adj_close    │       ├─────────────────┤
│    adj_volume   │       │ PK,FK instrument│
│    dividend     │       │ PK    tag       │
│    split_factor │       │    created_at   │
│    run_id       │       └─────────────────┘
│    created_at   │
└─────────────────┘       ┌─────────────────┐
                          │  pipeline_run   │
                          ├─────────────────┤
                          │ PK run_id       │
                          │    run_type     │
                          │    run_date     │
                          │    start_time   │
                          │    end_time     │
                          │    status       │
                          │    providers_run│
                          │    records_proc │
                          │    errors       │
                          │    tags_filter  │
                          │    created_at   │
                          └─────────────────┘
```

Implementation note: SQLAlchemy model table names in current code are `fact_feature` and `pipeline_run` (singular), even where examples in this document may use pluralized labels.

### 3.2 Table Specifications

#### dim_source
Metadata about data providers.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| source_id | INT | PK, IDENTITY | Unique identifier |
| name | VARCHAR(100) | NOT NULL, UNIQUE | Provider name (e.g., "tiingo") |
| provider_type | VARCHAR(50) | NOT NULL | Type: "market_data", "macro", "alternative" |
| base_url | VARCHAR(500) | | API base URL |
| is_active | BIT | DEFAULT 1 | Whether provider is enabled |
| created_at | DATETIME2 | DEFAULT GETUTCDATE() | Record creation time |
| updated_at | DATETIME2 | | Last update time |

#### dim_instrument
Master list of tradeable instruments.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| instrument_id | INT | PK, IDENTITY | Unique identifier |
| ticker | VARCHAR(20) | NOT NULL | Trading symbol |
| name | VARCHAR(255) | | Full instrument name |
| exchange | VARCHAR(50) | | Primary exchange |
| asset_type | VARCHAR(50) | NOT NULL | "equity", "etf", "fund", etc. |
| currency | VARCHAR(10) | DEFAULT 'USD' | Quote currency |
| sector | VARCHAR(100) | | GICS sector |
| industry | VARCHAR(100) | | GICS industry |
| country | VARCHAR(50) | | Country of domicile |
| is_active | BIT | DEFAULT 1 | Whether actively tracked |
| tiingo_ticker | VARCHAR(20) | | Tiingo-specific identifier |
| start_date | DATE | | First available data date |
| end_date | DATE | | Last available data date |
| created_at | DATETIME2 | DEFAULT GETUTCDATE() | Record creation time |
| updated_at | DATETIME2 | | Last update time |

**Index:** UNIQUE (ticker, exchange)

#### instrument_tag
Many-to-many relationship for instrument tagging (portfolios, watchlists, etc.).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| instrument_id | INT | PK, FK | Reference to dim_instrument |
| tag | VARCHAR(100) | PK | Tag name (e.g., "portfolio_main", "watchlist") |
| created_at | DATETIME2 | DEFAULT GETUTCDATE() | When tag was applied |

**Index:** (tag) for filtering by tag

#### dim_macro_series
Metadata for macroeconomic time series.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| series_id | INT | PK, IDENTITY | Unique identifier |
| fred_id | VARCHAR(50) | NOT NULL, UNIQUE | FRED series ID |
| name | VARCHAR(255) | NOT NULL | Human-readable name |
| category | VARCHAR(50) | NOT NULL | "growth", "liquidity", "risk_appetite" |
| subcategory | VARCHAR(100) | | More specific grouping |
| frequency | VARCHAR(20) | | "daily", "weekly", "monthly", "quarterly" |
| units | VARCHAR(100) | | Unit of measurement |
| seasonal_adj | VARCHAR(50) | | Seasonal adjustment type |
| description | TEXT | | Full description |
| is_active | BIT | DEFAULT 1 | Whether actively tracked |
| created_at | DATETIME2 | DEFAULT GETUTCDATE() | Record creation time |
| updated_at | DATETIME2 | | Last update time |

#### fact_ohlcv
Daily OHLCV price data with adjustments.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| instrument_id | INT | PK, FK | Reference to dim_instrument |
| trade_date | DATE | PK | Trading date |
| source_id | INT | FK | Reference to dim_source |
| open | DECIMAL(18,6) | | Raw open price |
| high | DECIMAL(18,6) | | Raw high price |
| low | DECIMAL(18,6) | | Raw low price |
| close | DECIMAL(18,6) | | Raw close price |
| volume | BIGINT | | Trading volume |
| adj_open | DECIMAL(18,6) | | Split/dividend adjusted open |
| adj_high | DECIMAL(18,6) | | Split/dividend adjusted high |
| adj_low | DECIMAL(18,6) | | Split/dividend adjusted low |
| adj_close | DECIMAL(18,6) | | Split/dividend adjusted close |
| adj_volume | BIGINT | | Adjusted volume |
| dividend | DECIMAL(18,6) | | Dividend amount |
| split_factor | DECIMAL(18,6) | | Split ratio |
| run_id | BIGINT | FK | Reference to pipeline_run |
| created_at | DATETIME2 | DEFAULT GETUTCDATE() | Record creation time |

**Index:** (trade_date), (instrument_id, trade_date DESC)

#### fact_macro
Macroeconomic indicator observations.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| series_id | INT | PK, FK | Reference to dim_macro_series |
| obs_date | DATE | PK | Observation date |
| source_id | INT | FK | Reference to dim_source |
| value | DECIMAL(18,6) | | Observation value |
| run_id | BIGINT | FK | Reference to pipeline_run |
| created_at | DATETIME2 | DEFAULT GETUTCDATE() | Record creation time |

**Index:** (obs_date), (series_id, obs_date DESC)

#### fact_feature
Engineered features derived from price/macro data.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| instrument_id | INT | PK, FK | Reference to dim_instrument |
| trade_date | DATE | PK | Calculation date |
| feature_name | VARCHAR(100) | PK | Feature identifier |
| source_id | INT | FK | Reference to dim_source (origin data) |
| value | DECIMAL(18,6) | | Calculated feature value |
| run_id | BIGINT | FK | Reference to pipeline_run |
| created_at | DATETIME2 | DEFAULT GETUTCDATE() | Record creation time |

**Index:** (trade_date), (feature_name, trade_date), (instrument_id, feature_name, trade_date DESC)

#### pipeline_run
Operational metadata for each pipeline execution.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| run_id | BIGINT | PK, IDENTITY | Unique run identifier |
| run_type | VARCHAR(50) | NOT NULL | "nightly", "backfill", "manual" |
| run_date | DATE | NOT NULL | Target date being processed |
| start_time | DATETIME2 | NOT NULL | Execution start |
| end_time | DATETIME2 | | Execution end |
| status | VARCHAR(20) | NOT NULL | "running", "success", "partial", "failed" |
| providers_run | VARCHAR(500) | | JSON array of providers executed |
| records_inserted | INT | | Count of new records |
| records_updated | INT | | Count of updated records |
| errors | TEXT | | Error messages if any |
| tags_filter | VARCHAR(500) | | JSON array of tags filtered (if subset run) |
| created_at | DATETIME2 | DEFAULT GETUTCDATE() | Record creation time |

**Index:** (run_date), (status), (run_type, run_date)

---

## 4. Provider Architecture

### 4.1 Provider Interface

All data providers implement a common interface:

```python
class BaseProvider(ABC):
    """Abstract base class for all data providers."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique provider identifier."""
        pass
    
    @property
    @abstractmethod
    def provider_type(self) -> str:
        """Provider category: 'market_data', 'macro', 'alternative'."""
        pass
    
    @abstractmethod
    async def fetch_data(
        self,
        date: datetime.date,
        instruments: Optional[List[str]] = None
    ) -> ProviderResult:
        """
        Fetch data for a specific date.
        
        Args:
            date: Target date to fetch
            instruments: Optional list of tickers (None = all available)
            
        Returns:
            ProviderResult with data and metadata
        """
        pass
    
    @abstractmethod
    async def fetch_instruments(self) -> List[InstrumentInfo]:
        """Fetch available instruments from this provider."""
        pass
    
    @abstractmethod
    def validate(self, data: pd.DataFrame) -> ValidationResult:
        """Validate fetched data against expected schema."""
        pass
```

### 4.2 Provider Registry

Providers are registered and managed through a central registry:

```python
class ProviderRegistry:
    """Central registry for data providers."""
    
    def register(self, provider: BaseProvider) -> None:
        """Register a provider instance."""
        
    def get(self, name: str) -> BaseProvider:
        """Get provider by name."""
        
    def get_active(self) -> List[BaseProvider]:
        """Get all active providers."""
        
    def get_by_type(self, provider_type: str) -> List[BaseProvider]:
        """Get providers by type."""
```

### 4.3 Implemented Providers

#### Tiingo Provider (V1)
- **Type:** market_data
- **Data:** Daily OHLCV for US equities, ETFs, mutual funds
- **Features:**
  - Supports adjusted and unadjusted prices
  - Provides dividend and split data
  - Bulk ticker list retrieval
  - Rate limiting handling

#### FRED Provider (V1)
- **Type:** macro
- **Data:** ~100 key macroeconomic series
- **Categories:**
  - Growth (GDP, employment, production)
  - Liquidity (money supply, rates, spreads)
  - Risk Appetite (VIX, credit spreads)

---

## 5. Feature Engine Architecture

Current repository state includes both legacy and V2 feature frameworks, but the pipeline orchestrator currently logs a placeholder for feature calculation and does not persist computed features through the run path yet.

### 5.1 Feature Interface

```python
class BaseFeature(ABC):
    """Abstract base class for engineered features."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique feature identifier."""
        pass
    
    @property
    @abstractmethod
    def dependencies(self) -> List[str]:
        """List of required input features/data."""
        pass
    
    @property
    @abstractmethod
    def lookback_days(self) -> int:
        """Number of historical days needed for calculation."""
        pass
    
    @abstractmethod
    def calculate(
        self,
        data: pd.DataFrame,
        date: datetime.date
    ) -> pd.Series:
        """
        Calculate feature values.
        
        Args:
            data: Historical data including dependencies
            date: Target calculation date
            
        Returns:
            Series indexed by instrument_id with feature values
        """
        pass
```

### 5.2 Feature Registry

```python
class FeatureRegistry:
    """Registry for feature definitions with dependency resolution."""
    
    def register(self, feature: BaseFeature) -> None:
        """Register a feature."""
        
    def get_calculation_order(self) -> List[BaseFeature]:
        """Return features in dependency-resolved order."""
        
    def calculate_all(
        self,
        data: pd.DataFrame,
        date: datetime.date
    ) -> pd.DataFrame:
        """Calculate all features for a date."""
```

### 5.3 Feature Categories (Extensible)

| Category | Example Features |
|----------|-----------------|
| **Returns** | daily_return, cumulative_return_5d, cumulative_return_21d |
| **Volatility** | realized_vol_21d, realized_vol_63d, vol_ratio |
| **Momentum** | rsi_14, macd, price_vs_sma_50, price_vs_sma_200 |
| **Volume** | volume_sma_20, relative_volume, obv |
| **Cross-sectional** | sector_relative_return, percentile_rank |

---

## 6. Pipeline Orchestration

### 6.1 Pipeline Modes

| Mode | Trigger | Description |
|------|---------|-------------|
| **Nightly** | Timer (cron) | Standard daily run for previous trading day |
| **Backfill** | Manual/API | Process historical date range |
| **Manual** | Manual/API | Ad-hoc single date run |

### 6.2 Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     Pipeline Orchestrator                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Initialize Run                                               │
│     └─► Create pipeline_run record (status: running)            │
│                                                                  │
│  2. Load Configuration                                           │
│     └─► Read active providers, instruments, tags filter          │
│                                                                  │
│  3. Execute Providers (parallel where possible)                  │
│     ┌─► For each active provider:                                │
│     │   ├─► Fetch data for target date                          │
│     │   ├─► Validate response                                    │
│     │   ├─► Archive raw data (Blob Storage)                      │
│     │   └─► Return ProviderResult                                │
│     └─► Collect all results, handle partial failures             │
│                                                                  │
│  4. Transform & Validate                                         │
│     ├─► Normalize schemas                                        │
│     ├─► Apply business rules                                     │
│     ├─► Quality checks (nulls, ranges, duplicates)               │
│     └─► Flag anomalies                                           │
│                                                                  │
│  5. Calculate Features                                           │
│     ├─► Load historical data for lookback                        │
│     ├─► Execute features in dependency order                     │
│     └─► Validate feature outputs                                 │
│                                                                  │
│  6. Persist to Database                                          │
│     ├─► Upsert fact_ohlcv                                        │
│     ├─► Upsert fact_macro                                        │
│     ├─► Upsert fact_feature                                      │
│     └─► Update dimension tables if needed                        │
│                                                                  │
│  7. Finalize Run                                                 │
│     ├─► Update pipeline_run (status, counts, errors)             │
│     ├─► Send notifications if errors                             │
│     └─► Log completion metrics                                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Current codepath note:

- Steps 1-3 and 6-7 are implemented in `PipelineOrchestrator`.
- Feature calculation (step 5) is currently a placeholder method.
- Raw archive and notification dispatch are described as target architecture; they are not actively executed in the orchestrator run path today.

### 6.3 Backfill Strategy

```python
async def run_backfill(
    start_date: date,
    end_date: date,
    providers: Optional[List[str]] = None,
    instruments: Optional[List[str]] = None,
    batch_size: int = 30  # days per batch
) -> BackfillResult:
    """
    Execute backfill for a date range.
    
    - Processes dates in batches to manage memory
    - Skips weekends/holidays for market data
    - Continues on partial failures
    - Logs progress and allows resume
    """
```

### 6.4 Idempotency

All writes use **upsert semantics** based on natural keys:
- `fact_ohlcv`: (instrument_id, trade_date)
- `fact_macro`: (series_id, obs_date)
- `fact_feature`: (instrument_id, trade_date, feature_name)

Re-running for the same date safely updates existing records.

---

## 7. Configuration Management

### 7.1 Configuration Hierarchy

```
config/
├── default.yaml          # Base configuration
├── providers/
│   └── fred_series.yaml  # FRED series definitions
├── instruments/
│   └── tags.yaml         # Instrument tag definitions
├── features/
│   └── registry.yaml     # Feature definitions
└── environments/
    ├── development.yaml  # Dev overrides
    └── production.yaml   # Prod overrides
```

### 7.2 Configuration Schema

```yaml
# default.yaml
pipeline:
  schedule: "0 0 * * *"  # Midnight UTC
  timezone: "America/New_York"
  completion_target_hour: 6  # Target completion by 6 AM ET
  
  retry:
    max_attempts: 3
    backoff_seconds: [60, 300, 900]
  
  parallel_providers: true
  batch_size_days: 30

database:
  driver: "mssql+pyodbc"
  connection_string_key: "atlas-db-connection"
  pool_size: 5
  max_overflow: 10

storage:
  raw_archive:
    enabled: true
    container: "atlas-raw"
    retention_days: 365
  connection_string_key: "atlas-storage-connection"

logging:
  level: "INFO"
  format: "json"
  
notifications:
  on_failure: true
  channels:
    email:
      enabled: true
      recipients_secret: "atlas-alert-emails"
```

### 7.3 Secrets Management

Secrets are resolved from environment variables first, then Azure Key Vault when configured.

| Secret Name | Description |
|-------------|-------------|
| `tiingo-api-key` | Tiingo API key |
| `fred-api-key` | FRED API key |
| `atlas-db-connection` | Database connection string |
| `atlas-storage-connection` | Blob storage connection string |
| `atlas-dashboard-users` | Dashboard user credentials JSON |
| `atlas-session-secret` | Dashboard session secret |
| `appinsights-connection` | Application Insights connection string |
| `atlas-alert-emails` | Failure notification recipients |

In Azure, application access is expected via Managed Identity.

---

## 8. Azure Infrastructure

### 8.1 Resource Overview

| Resource | Purpose | SKU/Tier |
|----------|---------|----------|
| **Resource Group** | Container for all resources | - |
| **Azure SQL Database** | Primary data store | Standard S2 (50 DTU) |
| **Azure Functions** | Pipeline execution | Consumption Plan |
| **Azure Container Apps** | Streamlit dashboard | Basic |
| **Azure Blob Storage** | Raw data archive | Standard LRS |
| **Azure Key Vault** | Secrets management | Standard |
| **Application Insights** | Monitoring & logging | Pay-as-you-go |

### 8.2 Network Architecture

```
┌────────────────────────────────────────────────────────────┐
│                    Azure Subscription                       │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Resource Group: atlas-rg                 │  │
│  │                                                       │  │
│  │  ┌─────────────┐     ┌─────────────┐                 │  │
│  │  │   Azure     │     │   Azure     │                 │  │
│  │  │  Functions  │────▶│    SQL      │                 │  │
│  │  │  (Pipeline) │     │  Database   │                 │  │
│  │  └──────┬──────┘     └──────▲──────┘                 │  │
│  │         │                   │                         │  │
│  │         │            ┌──────┴──────┐                 │  │
│  │         │            │  Container  │                 │  │
│  │         │            │    Apps     │◀────── Users    │  │
│  │         │            │ (Dashboard) │                 │  │
│  │         │            └─────────────┘                 │  │
│  │         │                                             │  │
│  │         ▼                                             │  │
│  │  ┌─────────────┐     ┌─────────────┐                 │  │
│  │  │    Blob     │     │  Key Vault  │                 │  │
│  │  │   Storage   │     │  (Secrets)  │                 │  │
│  │  └─────────────┘     └─────────────┘                 │  │
│  │                                                       │  │
│  │  ┌─────────────────────────────────────────────────┐ │  │
│  │  │         Application Insights (Monitoring)        │ │  │
│  │  └─────────────────────────────────────────────────┘ │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

### 8.3 Cost Estimate (Monthly)

| Resource | Estimated Cost |
|----------|---------------|
| Azure SQL (S2) | ~$75 |
| Azure Functions (Consumption) | ~$5-20 |
| Container Apps (Basic) | ~$15-30 |
| Blob Storage (100GB) | ~$2 |
| Key Vault | ~$1 |
| Application Insights | ~$5-10 |
| **Total** | **~$100-140/month** |

---

## 9. Security Architecture

### 9.1 Authentication & Authorization

| Component | Auth Method |
|-----------|-------------|
| Dashboard | Username/Password (V1), Azure AD (V2) |
| Database | Azure AD + Managed Identity |
| Key Vault | Managed Identity |
| APIs | API Key in header |

### 9.2 Security Controls

- **Encryption at rest:** Azure SQL TDE, Blob Storage encryption
- **Encryption in transit:** TLS 1.2+ for all connections
- **Network:** Private endpoints (optional), IP restrictions
- **Secrets:** All credentials in Key Vault, referenced via Managed Identity
- **Least privilege:** Separate read/write DB users, minimal RBAC roles

---

## 10. Monitoring & Observability

### 10.1 Metrics

| Metric | Description | Alert Threshold |
|--------|-------------|-----------------|
| `pipeline.duration_seconds` | Total run time | > 7200 (2 hours) |
| `pipeline.records_processed` | Records per run | < expected -20% |
| `pipeline.errors_count` | Errors per run | > 0 |
| `provider.fetch_duration` | Per-provider fetch time | > 600 (10 min) |
| `provider.records_fetched` | Records per provider | < expected -20% |

### 10.2 Logging

Structured JSON logs with:
- `timestamp`, `level`, `message`
- `run_id`, `provider`, `operation`
- `duration_ms`, `record_count`
- `error_type`, `error_message`, `stack_trace`

### 10.3 Alerts

| Alert | Condition | Channel |
|-------|-----------|---------|
| Pipeline Failed | status = "failed" | Email |
| Pipeline Delayed | end_time > 06:00 ET | Email |
| Provider Error | provider error count > 0 | Email |
| Data Anomaly | volume < 80% of avg | Email |

---

## 11. Testing Strategy

Current repository note: `pyproject.toml` defines pytest settings, but there are no committed `tests/` files in this snapshot.

### 11.1 Test Categories

| Category | Scope | Tools |
|----------|-------|-------|
| **Unit** | Individual functions | pytest |
| **Integration** | Provider + DB | pytest + testcontainers |
| **Contract** | API responses | pytest + schema validation |
| **E2E** | Full pipeline | pytest + test DB |

### 11.2 Test Data

- Synthetic data generators for each table
- Recorded API responses for provider tests
- Test database with known data for validation

---

## 12. Deployment & Operations

### 12.1 Deployment Pipeline

```
┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
│  Code   │───▶│  Build  │───▶│  Test   │───▶│ Deploy  │
│ Commit  │    │ & Lint  │    │  Suite  │    │ (Azure) │
└─────────┘    └─────────┘    └─────────┘    └─────────┘
```

### 12.2 Operational Procedures

| Procedure | Command |
|-----------|---------|
| Manual run | `atlas run --date 2026-01-25` |
| Backfill | `atlas backfill --start 2020-01-01 --end 2026-01-25` (interactive confirm) |
| Backfill dry-run | `atlas backfill --start 2020-01-01 --end 2026-01-25 --dry-run` |
| Local validation | `python scripts/validate_local.py` |
| Add provider | Create provider class, register in config |
| Add feature | Implement in legacy or V2 feature path; orchestrator integration is pending |
| View logs | Azure Portal > Application Insights |

---

## 13. Future Roadmap

### V1.1
- Additional providers (EODHistoricalData, Polygon)
- Enhanced dashboard visualizations
- Azure AD SSO integration

### V1.2
- API layer (FastAPI) for programmatic access
- Advanced alerting with anomaly detection
- Feature versioning

### V2.0
- Backtesting module
- Portfolio optimization toolkit
- Data lake integration (Parquet/Delta)

---

## Appendix A: FRED Macro Series (Initial Set)

### Growth Indicators
| FRED ID | Name | Frequency |
|---------|------|-----------|
| GDP | Gross Domestic Product | Quarterly |
| GDPC1 | Real GDP | Quarterly |
| PAYEMS | Total Nonfarm Payrolls | Monthly |
| UNRATE | Unemployment Rate | Monthly |
| ICSA | Initial Jobless Claims | Weekly |
| INDPRO | Industrial Production Index | Monthly |
| RSXFS | Retail Sales Ex Food Services | Monthly |
| UMCSENT | Consumer Sentiment | Monthly |
| HOUST | Housing Starts | Monthly |
| PERMIT | Building Permits | Monthly |
| DGORDER | Durable Goods Orders | Monthly |
| NEWORDER | New Orders | Monthly |
| ISM-PMI | ISM Manufacturing PMI | Monthly |
| ISM-NMI | ISM Non-Manufacturing Index | Monthly |

### Liquidity Indicators
| FRED ID | Name | Frequency |
|---------|------|-----------|
| M2SL | M2 Money Stock | Weekly |
| BOGMBASE | Monetary Base | Biweekly |
| WALCL | Fed Total Assets | Weekly |
| FEDFUNDS | Federal Funds Rate | Daily |
| DFF | Effective Fed Funds Rate | Daily |
| DGS2 | 2-Year Treasury | Daily |
| DGS10 | 10-Year Treasury | Daily |
| DGS30 | 30-Year Treasury | Daily |
| T10Y2Y | 10Y-2Y Spread | Daily |
| T10Y3M | 10Y-3M Spread | Daily |
| TEDRATE | TED Spread | Daily |
| BAMLH0A0HYM2 | HY OAS | Daily |
| BAMLC0A4CBBB | BBB OAS | Daily |
| SOFR | SOFR Rate | Daily |

### Risk Appetite Indicators
| FRED ID | Name | Frequency |
|---------|------|-----------|
| VIXCLS | VIX Index | Daily |
| BAMLH0A0HYM2EY | HY Yield | Daily |
| BAMLC0A4CBBBEY | BBB Yield | Daily |
| SP500 | S&P 500 | Daily |
| NASDAQCOM | NASDAQ Composite | Daily |
| DTWEXBGS | Trade Weighted Dollar | Daily |
| DCOILWTICO | WTI Crude Oil | Daily |
| GOLDAMGBD228NLBM | Gold Price | Daily |
| CPIAUCSL | CPI All Items | Monthly |
| CPILFESL | Core CPI | Monthly |
| PCEPI | PCE Price Index | Monthly |
| PCEPILFE | Core PCE | Monthly |
| T5YIE | 5Y Breakeven Inflation | Daily |
| T10YIE | 10Y Breakeven Inflation | Daily |

---

## Appendix B: Glossary

| Term | Definition |
|------|------------|
| **OHLCV** | Open, High, Low, Close, Volume - standard price bar data |
| **Adjusted Price** | Price corrected for splits and dividends |
| **Backfill** | Process of loading historical data |
| **Provider** | External data source adapter |
| **Feature** | Derived/calculated metric from raw data |
| **Idempotent** | Operation that produces same result if repeated |
| **Upsert** | Insert or update based on key existence |
