# ATLAS V1 - System Architecture Document

## Document Information
| Field | Value |
|-------|-------|
| Version | 1.0.1 |
| Last Updated | 2026-07-27 |
| Status | Implementation status and target architecture |

---

## 1. Executive Summary

ATLAS V1 is a data pipeline designed for institutional investment management. The implemented repository provides CLI-driven collection of market data and macroeconomic indicators, validation, relational storage, historical backfill, and a Streamlit dashboard. The Azure infrastructure, scheduler settings, raw archive configuration, and notification settings describe the target operating model; the source tree does not yet include an Azure Functions timer entrypoint, blob archive writer, or notification sender.

### Key Capabilities
- **Multi-provider data ingestion** with modular architecture
- **Historical backfill** support for any date range
- **Feature engineering framework** for derived analytics; pipeline integration is still a placeholder
- **Portfolio tagging** to track instrument subsets
- **Macro indicator categorization** (Growth, Liquidity, Risk Appetite)
- **Streamlit dashboard** with login authentication (role helpers exist but are unused by pages)
- **Cloud-agnostic design** with Azure as primary deployment target

### Current Runtime Boundary

The codepaths that execute today are:

- `atlas run`, `atlas backfill`, `atlas status`, `atlas init-db`, `atlas instruments`, and `atlas dashboard` in `src/atlas/cli/main.py`
- `PipelineOrchestrator` in `src/atlas/pipeline/orchestrator.py`
- provider adapters under `src/atlas/providers/`
- SQLAlchemy storage under `src/atlas/storage/`
- Feature Engine V2 library under `src/atlas/features/` (callable directly; not invoked by the orchestrator)
- Streamlit dashboard under `src/atlas/dashboard/`
- Local helpers: `scripts/validate_local.py`, `scripts/backfill_5year.py`

The following are configured or provisioned but not wired into the runtime yet: Azure Functions scheduling, raw payload archival to Blob Storage, email/alert notifications, orchestrator → FeatureEngineV2 persistence, and dashboard role enforcement / production fail-closed auth.

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
│  │     Azure Blob Storage (Raw Archive) — config/IaC only today         │   │
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
│  │  │  (login) │ │  View    │ │  View    │ │  (stub)  │               │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        ORCHESTRATION LAYER                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              CLI today / Azure Functions Timer target                 │   │
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

| Component | Responsibility | Azure Service | Current repository status |
|-----------|---------------|---------------|---------------------------|
| **Provider Registry** | Manages data source adapters | Azure Functions target | Implemented in `src/atlas/providers/registry.py` |
| **Validation Engine** | Provider schema and quality checks | Azure Functions target | Implemented in provider adapters |
| **Transformation Engine** | Data normalization | Azure Functions target | Implemented in provider adapters and persistence code |
| **Feature Engine** | Derived metric calculation | Azure Functions target | Library/catalog implemented; orchestrator hook is a placeholder |
| **Primary Storage** | Relational data store | Azure SQL Database | Implemented through SQLAlchemy; SQLite fallback for local development |
| **Raw Archive** | Source data preservation | Azure Blob Storage | Config and infrastructure only; no writer is implemented |
| **Dashboard** | User interface | Azure Container Apps | Implemented as a Streamlit app with login gate; RBAC helpers unused |
| **Orchestrator** | Pipeline execution | Azure Functions Timer target | Implemented as CLI-driven `PipelineOrchestrator`; no timer entrypoint |
| **Secrets Management** | Credentials storage | Azure Key Vault | Environment variables first, then Key Vault, then SQLite DB fallback |
| **Monitoring** | Logs and metrics | Application Insights | Structured logging exists; alert metrics are target-state |

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
│   fact_ohlcv    │       │  fact_feature   │       │   fact_macro    │
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
│    adj_low      │       │ instrument_tag   │
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

┌──────────────────────┐
│ feature_diagnostic   │
├──────────────────────┤
│ PK diagnostic_id     │
│    feature_name      │
│    calc_date         │
│    forward_horizon   │
│    ic / hit_rate     │
│    regime / run_id   │
└──────────────────────┘
```

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
Engineered features derived from price/macro data. The table and repository upsert path exist; the nightly orchestrator does not populate this table yet.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| instrument_id | INT | PK, FK | Reference to dim_instrument |
| trade_date | DATE | PK | Calculation date |
| feature_name | VARCHAR(100) | PK | Feature identifier |
| source_id | INT | FK | Reference to dim_source (origin data) |
| value | DECIMAL(18,6) | | Calculated feature value |
| feature_version | VARCHAR(20) | | Feature definition version |
| params_hash | VARCHAR(64) | | Parameter fingerprint |
| transform_type | VARCHAR(20) | | `raw`, `rank`, or `zscore` |
| input_vintage | DATETIME2 | | Input data vintage |
| calc_timestamp | DATETIME2 | | Calculation timestamp |
| run_id | BIGINT | FK | Reference to pipeline_run |
| created_at | DATETIME2 | DEFAULT GETUTCDATE() | Record creation time |

**Index:** (trade_date), (feature_name, trade_date), (instrument_id, feature_name, trade_date DESC), (feature_name, feature_version)

#### feature_diagnostic
Feature quality metrics (IC, hit rate). Schema exists; `FeatureEngineV2` currently defers diagnostics persistence when future returns are unavailable.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| diagnostic_id | BIGINT | PK, IDENTITY | Unique identifier |
| feature_name | VARCHAR(100) | NOT NULL | Feature identifier |
| feature_version | VARCHAR(20) | | Feature definition version |
| universe_scope | VARCHAR(50) | DEFAULT 'all' | Universe label |
| calc_date | DATE | NOT NULL | Diagnostic calculation date |
| forward_horizon | INT | NOT NULL | Forward return horizon (e.g. 5/21/63/126) |
| ic_spearman | DECIMAL(10,6) | | Spearman IC |
| ic_pearson | DECIMAL(10,6) | | Pearson IC |
| hit_rate | DECIMAL(10,6) | | Directional hit rate |
| t_stat | DECIMAL(10,6) | | t-statistic |
| n_observations | INT | | Observation count |
| regime | VARCHAR(20) | DEFAULT 'all' | Regime label |
| run_id | BIGINT | FK | Reference to pipeline_run |
| created_at | DATETIME2 | DEFAULT GETUTCDATE() | Record creation time |

**Index:** (feature_name, calc_date), (forward_horizon), (regime)

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

### Implementation Status

Feature code exists in two layers:

- **V2 (current):** `src/atlas/features/schema.py` `FEATURE_CATALOG` is the source of truth. `FeatureEngineV2` / `calculate_features()` in `engine_v2.py` can calculate and persist features when invoked directly against OHLCV history.
- **V1 (legacy):** `FeatureEngine` + `FeatureRegistry` remain for compatibility. Neither V1 nor V2 reads `config/features/registry.yaml`.
- **Pipeline:** `PipelineOrchestrator._calculate_features()` only logs a placeholder, so `atlas run` / `atlas backfill` do not populate `fact_feature`.
- **Dashboard:** Features page is a stub.
- **Diagnostics:** `feature_diagnostic` table exists; engine diagnostics persistence is currently deferred when future returns are unavailable.

### 5.1 Preferred Extension Path (V2)

Add or update feature definitions via `register_feature(...)` in `src/atlas/features/schema.py`, implement or extend a family generator under `src/atlas/features/generators.py`, then invoke:

```python
from datetime import date
from atlas.features import calculate_features, FeatureEngineConfig

result = await calculate_features(
    target_date=date(2026, 1, 24),
    config=FeatureEngineConfig(max_priority=3, apply_transforms=True),
)
```

Wire `FeatureEngineV2` into `PipelineOrchestrator._calculate_features()` before expecting nightly feature persistence.

### 5.2 Legacy V1 Interface (compatibility only)

`BaseFeature` / `FeatureRegistry` remain exported for backward compatibility. Prefer V2 schema + generators for new work.

### 5.3 Feature Families (V2)

| Family | Role |
|--------|------|
| Momentum / Trend / Breakout | Price-path signals across lookback horizons |
| Mean Reversion | Reversion and range features |
| Factor | Factor-ETF relative exposures |
| Risk | Volatility and drawdown-style measures |
| UDR / Regime | Custom and regime conditioning features |
| Transforms | Cross-sectional rank / z-score variants via `PanelTransformer` |

---

## 6. Pipeline Orchestration

### 6.1 Pipeline Modes

| Mode | Trigger | Description |
|------|---------|-------------|
| **Nightly** | Planned timer (cron) | Target standard daily run for previous trading day; cron config exists, but no scheduler entrypoint is implemented |
| **Backfill** | CLI | Process historical date range with batches and an interactive confirmation prompt |
| **Manual** | CLI | Ad-hoc single date run through `atlas run`; this is the only single-run mode wired today |

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
│     │   ├─► Raw archive planned; no Blob writer is called today  │
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
│     └─► Placeholder log in orchestrator; no features persisted   │
│                                                                  │
│  6. Persist to Database                                          │
│     ├─► Upsert fact_ohlcv                                        │
│     ├─► Upsert fact_macro                                        │
│     ├─► Upsert fact_feature (planned; not called today)          │
│     └─► Update dimension tables if needed                        │
│                                                                  │
│  7. Finalize Run                                                 │
│     ├─► Update pipeline_run (status, counts, errors)             │
│     ├─► Notifications planned; no sender is called today         │
│     └─► Log completion metrics                                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

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

Implemented fact-table writes use **upsert semantics** based on natural keys:
- `fact_ohlcv`: (instrument_id, trade_date)
- `fact_macro`: (series_id, obs_date)
- `fact_feature`: (instrument_id, trade_date, feature_name)

`fact_feature` has the same natural key in the model, but the pipeline does not write it yet. Re-running implemented price and macro ingestion for the same date safely updates existing records.

---

## 7. Configuration Management

### 7.1 Configuration Hierarchy

```
config/
├── default.yaml          # Base configuration
├── providers/
│   └── fred_series.yaml  # FRED series definitions
├── instruments/
│   └── tags.yaml         # Portfolio/tag definitions
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
  schedule: "0 5 * * *"  # Config only; no scheduler entrypoint yet
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

The raw archive and notification blocks are configuration only in the current codebase. The CLI and dashboard read process environment variables directly and do **not** call `load_dotenv()`. Only `scripts/validate_local.py` and `scripts/backfill_5year.py` load `.env` automatically.

### 7.3 Secrets Management

Secrets can be read from environment variables or Azure Key Vault:

| Secret / Env | Description | Runtime notes |
|--------------|-------------|---------------|
| `TIINGO_API_KEY` / `tiingo-api-key` | Tiingo API key | Provider checks env, then Key Vault |
| `FRED_API_KEY` / `fred-api-key` | FRED API key | Provider checks env, then Key Vault |
| `ATLAS_DB_CONNECTION` / `atlas-db-connection` | Database connection string | Env → Key Vault → SQLite fallback |
| `ATLAS_DASHBOARD_USERS` | Dashboard username → SHA-256 hash JSON | Used by `dashboard/auth.py`; Key Vault users path is not wired |
| `ATLAS_KEYVAULT_URL` | Key Vault URL | Used by secrets helper |

For database connections, `src/atlas/storage/database.py` checks `ATLAS_DB_CONNECTION` first, then Key Vault using `atlas-db-connection`, then falls back to `sqlite:///atlas_dev.db` for local development.

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

| Component | Auth Method | Current status |
|-----------|-------------|----------------|
| Dashboard | Username/password via `ATLAS_DASHBOARD_USERS` or hard-coded development defaults | Login gate enforced when `dashboard.auth.enabled`; `require_role()` is unused by pages |
| Dashboard defaults | `admin` / `analyst` with password `atlas123` when env JSON missing/invalid | Fail-open today even if `ATLAS_ENV=production` |
| Database | Connection string / Azure AD + Managed Identity (target) | Local SQLite fallback when connection secret missing |
| Key Vault | Managed Identity (target) | Used when `ATLAS_KEYVAULT_URL` is set and env secret missing |
| APIs | API key in header | Provider API keys only; no public ATLAS API yet |

### 9.2 Security Controls

- **Encryption at rest:** Azure SQL TDE, Blob Storage encryption (target Azure posture)
- **Encryption in transit:** TLS 1.2+ for all connections
- **Network:** Private endpoints (optional), IP restrictions
- **Secrets:** Prefer exported environment variables for local CLI/dashboard; Key Vault for Azure deployments; avoid credentials in code
- **Least privilege:** Separate read/write DB users, minimal RBAC roles (target)
- **Operational pitfall:** set a valid `ATLAS_DASHBOARD_USERS` map before any shared/production deployment; defaults are intentional for local development only

---

## 10. Monitoring & Observability

The current implementation writes structured logs and run metadata to `pipeline_run`. Application Insights metrics and alert thresholds below describe the intended Azure operating model, not emitted custom metrics in the checked-in code.

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

Alert configuration exists in `config/default.yaml`, but no notification sender is implemented today.

| Planned alert | Condition | Planned channel |
|---------------|-----------|-----------------|
| Pipeline Failed | status = "failed" | Email |
| Pipeline Delayed | end_time > 06:00 ET | Email |
| Provider Error | provider error count > 0 | Email |
| Data Anomaly | volume < 80% of avg | Email |

---

## 11. Testing Strategy

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
| Backfill | `atlas backfill --start 2020-01-01 --end 2026-01-25 --batch-size 30` |
| Preview backfill | `atlas backfill --start 2020-01-01 --end 2026-01-25 --dry-run` |
| Check database and latest run | `atlas status` |
| Initialize local database | `atlas init-db` |
| Recreate local database | `atlas init-db --force` after confirming the destructive prompt |
| Validate local setup | `python3 scripts/validate_local.py` (loads `.env`, seeds instruments from `ATLAS_INPUT_TEMPLATE_V1.csv`) |
| Bulk historical helper | `python3 scripts/backfill_5year.py` (loads `.env`; separate from `atlas backfill`) |
| Launch dashboard | From repo root: `atlas dashboard` |
| Standalone features | Call `atlas.features.calculate_features(...)` after OHLCV history exists |
| Add provider | Create provider class, register it in `src/atlas/providers/registry.py`, and add configuration if needed |
| Add feature | Register in `src/atlas/features/schema.py`; wire orchestrator to `FeatureEngineV2` before expecting pipeline output |
| View logs | CLI output or configured structured logs; Application Insights is target-state |

### 12.3 Common Pitfalls

| Pitfall | Detail |
|---------|--------|
| `.env` not loaded by CLI | Export vars or `source .env` before `atlas` commands |
| Empty instruments | Load via `validate_local.py` / CSV bootstrap; `instruments sync` is not implemented |
| Empty `fact_feature` after pipeline | Expected until orchestrator wiring lands |
| Dashboard path errors | CLI uses relative `src/atlas/dashboard/app.py`; run from repo root |
| Default dashboard passwords in shared envs | Auth falls back to development defaults when `ATLAS_DASHBOARD_USERS` is unset/invalid |

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
