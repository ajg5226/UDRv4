# ATLAS V1 - System Architecture Document

## Document Information
| Field | Value |
|-------|-------|
| Version | 1.1.0 |
| Last Updated | 2026-05-18 |
| Status | Implementation Aligned |

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
| **Feature Engine** | Derived metric calculation; V2 engine implemented, orchestrator wiring pending | Azure Functions |
| **Primary Storage** | Relational data store | Azure SQL Database |
| **Raw Archive** | Source data preservation; config/IaC present, application archiving pending | Azure Blob Storage |
| **Dashboard** | User interface | Azure Container Apps |
| **Orchestrator** | Pipeline scheduling; CLI entrypoint implemented, Function host not included in `src/` | Azure Functions Timer |
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
│   fact_ohlcv    │       │  fact_feature   │       │   fact_macro    │
├─────────────────┤       ├─────────────────┤       ├─────────────────┤
│ PK,FK instrument│       │ PK,FK instrument│       │ PK,FK series_id │
│ PK    trade_date│       │ PK    trade_date│       │ PK    obs_date  │
│ FK    source_id │       │ PK    feature   │       │ FK    source_id │
│    open         │       │ FK    source_id │       │    value        │
│    high         │       │    value        │       │    run_id       │
│    low          │       │    feature_ver  │       │    created_at   │
│    close        │       │    params_hash  │       └─────────────────┘
│    volume       │       │    transform    │
│                 │       │    calc_ts      │
│                 │       │    run_id       │
│                 │       │    created_at   │
│                 │       └─────────────────┘
│    adj_open     │
│    adj_high     │       ┌─────────────────┐
│    adj_low      │       │ instrument_tag  │
│    adj_close    │       ├─────────────────┤
│    adj_volume   │       │ PK,FK instrument│
│    dividend     │       │ PK    tag       │
│    split_factor │       │    created_at   │
│    run_id       │       └─────────────────┘
│    created_at   │
└─────────────────┘       ┌─────────────────┐
                          │feature_diagnostic
                          ├─────────────────┤
                          │ PK diagnostic_id│
                          │    feature_name │
                          │    calc_date    │
                          │    horizon      │
                          │    ic_spearman  │
                          │    hit_rate     │
                          │    regime       │
                          │    run_id       │
                          └─────────────────┘
                          ┌─────────────────┐
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
| source_id | INT | FK, nullable | Optional reference to dim_source |
| value | DECIMAL(18,6) | | Calculated feature value |
| feature_version | VARCHAR(20) | | Feature implementation version |
| params_hash | VARCHAR(64) | | Hash for calculation parameters |
| transform_type | VARCHAR(20) | | raw, rank, zscore, quintile, or decile |
| input_vintage | DATETIME2 | | Optional input data vintage |
| calc_timestamp | DATETIME2 | | Calculation timestamp |
| run_id | BIGINT | FK | Reference to pipeline_run |
| created_at | DATETIME2 | DEFAULT GETUTCDATE() | Record creation time |

**Index:** (trade_date), (feature_name, trade_date), (instrument_id, feature_name, trade_date), (feature_name, feature_version)

#### feature_diagnostic
Feature quality diagnostics for signal monitoring and research review.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| diagnostic_id | BIGINT | PK, IDENTITY | Unique diagnostic identifier |
| feature_name | VARCHAR(100) | NOT NULL | Feature identifier |
| feature_version | VARCHAR(20) | | Feature implementation version |
| universe_scope | VARCHAR(50) | DEFAULT 'all' | Instrument universe used |
| calc_date | DATE | NOT NULL | Feature calculation date |
| forward_horizon | INT | NOT NULL | Forward return horizon, e.g. 5, 21, 63, 126 |
| ic_spearman | DECIMAL(10,6) | | Rank information coefficient |
| ic_pearson | DECIMAL(10,6) | | Linear information coefficient |
| hit_rate | DECIMAL(10,6) | | Sign correctness rate |
| t_stat | DECIMAL(10,6) | | Statistical significance estimate |
| n_observations | INT | | Number of aligned observations |
| regime | VARCHAR(20) | DEFAULT 'all' | Regime label |
| run_id | BIGINT | FK | Reference to pipeline_run |
| created_at | DATETIME2 | DEFAULT GETUTCDATE() | Record creation time |

**Index:** (feature_name, calc_date), (forward_horizon), (regime)

Diagnostics storage exists in the schema. Runtime calculation is currently
deferred in `FeatureEngineV2` because IC and hit-rate metrics require future
returns relative to the feature calculation date.

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

The implemented V2 feature engine is catalog-driven, not class-per-feature.
`src/atlas/features/schema.py` defines `FEATURE_CATALOG` as the source of truth,
and `src/atlas/features/engine_v2.py` coordinates calculation.

### 5.1 Feature Definition Contract

```python
@dataclass
class FeatureDefinition:
    name: str
    family: FeatureFamily
    description: str
    horizon_family: HorizonFamily
    lookback_days: int
    min_history: int
    parameters: dict[str, Any] = field(default_factory=dict)
    lookback_variants: list[int] = field(default_factory=list)
    directionality: Directionality = Directionality.HIGHER_BETTER
    transforms: list[TransformType] = field(default_factory=lambda: [TransformType.RAW])
    requires: list[DataRequirement] = field(default_factory=lambda: [DataRequirement.OHLCV])
    depends_on_features: list[str] = field(default_factory=list)
    universe_scope: str = "all"
    enabled: bool = True
    priority: int = 1
    version: str = "1.0.0"
```

Feature names are generated as `<base_name>_<lookback>d[_<transform>]`.
For example, `mom_ts` with 21-day lookback and rank transform becomes
`mom_ts_21d_rank`.

### 5.2 Calculation Flow

1. `FeatureEngineV2` selects enabled definitions by priority and family.
2. The engine loads OHLCV history from `OHLCVRepository`.
3. Benchmark and factor ETF history are loaded when required and available
   (`SPY`, `MTUM`, `QUAL`, `USMV`, `VLUE`, `IWM`, sector ETFs).
4. The engine routes each feature to the generator for its `FeatureFamily`.
5. Raw variants are calculated for each lookback.
6. `PanelTransformer` applies cross-sectional transforms.
7. Non-null values are upserted to `fact_feature` with version and lineage
   metadata.

### 5.3 Feature Families and Transforms

| Family | Example Features |
|--------|------------------|
| **Momentum** | `mom_ts`, `mom_risk_adj`, `mom_residual` |
| **Trend** | `trend_slope`, `trend_adx`, `trend_efficiency` |
| **Breakout** | `breakout_high`, `breakout_dist_high` |
| **Mean Reversion** | `mr_zscore`, `mr_reversal`, `mr_rsi` |
| **Factor** | `factor_beta_spy`, `factor_beta_qual` |
| **Risk** | `risk_realized_vol`, `risk_drawdown` |
| **UDR/Capture** | `udr_up_capture`, `udr_down_capture` |
| **Regime** | `regime_hurst`, `regime_corr_spy` |

Panel transforms currently support:

- `raw`: original calculated value.
- `rank`: percentile rank from 0 to 100.
- `zscore`: 2.5% winsorized z-score clipped to +/-3.
- `quintile`: bucket 1 to 5.
- `decile`: bucket 1 to 10.

See `docs/FEATURE_ENGINE.md` for operational usage, current catalog counts,
and constraints.

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
│     │   ├─► Raw archive config exists; app archiving is pending  │
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
│     └─► V2 engine implemented; orchestrator hook pending         │
│                                                                  │
│  6. Persist to Database                                          │
│     ├─► Upsert fact_ohlcv                                        │
│     ├─► Upsert fact_macro                                        │
│     ├─► Upsert fact_feature (when feature engine is invoked)     │
│     └─► Update dimension tables if needed                        │
│                                                                  │
│  7. Finalize Run                                                 │
│     ├─► Update pipeline_run (status, counts, errors)             │
│     ├─► Send notifications if errors                             │
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
│   └── tags.yaml         # Portfolio/watchlist tag definitions
├── features/
│   └── registry.yaml     # Legacy feature config path
└── environments/
    ├── development.yaml  # Dev overrides
    └── production.yaml   # Prod overrides
```

Provider settings for Tiingo and FRED live in `config/default.yaml` and can be
overridden by environment files. Feature Engine V2 reads its canonical catalog
from `src/atlas/features/schema.py`; `config/features/registry.yaml` remains in
the tree for the legacy feature engine/configuration path.

### 7.2 Configuration Schema

```yaml
# default.yaml
pipeline:
  schedule: "0 5 * * *"  # 5 AM UTC
  timezone: "America/New_York"
  completion_target_hour: 6  # Target completion by 6 AM ET
  
  retry:
    max_attempts: 3
    backoff_seconds: [60, 300, 900]
  
  parallel_providers: true
  max_parallel_workers: 4
  batch_size_days: 30
  default_providers:
    - tiingo
    - fred

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

providers:
  tiingo:
    api_key_secret: "tiingo-api-key"
    base_url: "https://api.tiingo.com"
  fred:
    api_key_secret: "fred-api-key"
    series_config: "config/providers/fred_series.yaml"

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

Secrets are resolved by `atlas.core.secrets` in this order:

1. Environment variable matching the secret name uppercased with hyphens
   converted to underscores, e.g. `tiingo-api-key` -> `TIINGO_API_KEY`.
2. Azure Key Vault when `ATLAS_KEYVAULT_URL` is set.
3. The caller-provided default, if any.

Configured secret names:

| Secret Name | Description |
|-------------|-------------|
| `tiingo-api-key` | Tiingo API key |
| `fred-api-key` | FRED API key |
| `atlas-db-connection` | Database connection string |
| `atlas-storage-connection` | Blob storage connection string |
| `atlas-dashboard-users` | Dashboard user credentials JSON |
| `atlas-session-secret` | Streamlit session secret |
| `appinsights-connection` | Application Insights connection string |
| `atlas-alert-emails` | Comma-separated alert recipients |

Application accesses via Managed Identity (no credentials in code).

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
| Backfill | `atlas backfill --start 2020-01-01 --end 2026-01-25` |
| Add provider | Create provider class, register in config |
| Add feature | Create feature class, register in config |
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
