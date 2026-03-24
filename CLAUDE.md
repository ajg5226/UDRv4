# CLAUDE.md — AI Assistant Guide for ATLAS V1 (UDRv4)

This document describes the codebase structure, development conventions, and key workflows for AI assistants working in this repository.

---

## Project Overview

**ATLAS V1** is a financial data pipeline and feature engineering platform built in Python. It collects market data (Tiingo) and macro data (FRED), stores it in a star-schema database, calculates financial features, and exposes a Streamlit dashboard for exploration.

- **Python version**: 3.11+
- **Package manager**: Poetry (`pyproject.toml`)
- **Main package**: `src/atlas/` (installed as `atlas`)
- **CLI entry point**: `poetry run atlas`

---

## Repository Structure

```
UDRv4/
├── config/                          # YAML configuration files
│   ├── default.yaml                 # Main app configuration
│   ├── environments/
│   │   ├── development.yaml         # Dev overrides (SQLite, debug logging)
│   │   └── production.yaml          # Prod overrides (SQL Server, App Insights)
│   ├── features/
│   │   └── registry.yaml            # Feature definitions and parameters
│   ├── instruments/
│   │   └── tags.yaml                # Portfolio/watchlist/sector tag definitions
│   └── providers/
│       └── fred_series.yaml         # FRED macro series configuration
│
├── docs/
│   └── ARCHITECTURE_DOCUMENT.md     # Full system design documentation
│
├── infrastructure/
│   └── azure/                       # Azure IaC (Bicep templates)
│       ├── deploy.sh
│       ├── main.bicep
│       └── modules/                 # appinsights, containerapp, functionapp,
│                                    # keyvault, sql, storage
│
├── scripts/
│   ├── backfill_5year.py            # Standalone historical backfill script
│   └── validate_local.py            # Local environment validation
│
├── src/atlas/                       # Main Python package
│   ├── cli/                         # Typer CLI commands
│   ├── core/                        # Config, logging, exceptions, secrets
│   ├── providers/                   # Data provider adapters (Tiingo, FRED)
│   ├── storage/                     # SQLAlchemy ORM, repository pattern
│   ├── features/                    # Feature engineering engine
│   ├── pipeline/                    # Orchestrator and backfill manager
│   └── dashboard/                   # Streamlit web interface
│
├── pyproject.toml                   # Project metadata, dependencies, tooling
├── requirements.txt                 # Pip-compatible requirements
├── .env.example                     # Environment variable template
├── README.md                        # End-user documentation
└── ATLAS_V1_PRD.md                  # Product requirements document
```

---

## Module Architecture

Data flows through layers in this order:

```
External APIs (Tiingo / FRED)
        ↓
    Providers  (src/atlas/providers/)
        ↓
Pipeline Orchestrator  (src/atlas/pipeline/orchestrator.py)
        ↓
    Storage Layer  (src/atlas/storage/)
        ↓
   Database (SQLite / Azure SQL)
        ↓
  Feature Engine  (src/atlas/features/)
        ↓
  Dashboard / CLI  (src/atlas/dashboard/ | src/atlas/cli/)
```

### `core/` — Shared Utilities

| File | Purpose |
|------|---------|
| `config.py` | Pydantic v2 settings, YAML loading, env var overrides (`ATLAS_*` prefix). Singleton via `get_settings()`. |
| `exceptions.py` | Exception hierarchy rooted at `AtlasError`. Types: `ConfigurationError`, `ProviderError`, `DatabaseError`, `ValidationError`, `PipelineError`, `RateLimitError`, `DataQualityError`. |
| `logging.py` | `structlog` structured logging. JSON in prod, colored console in dev. Context managers: `LogContext`, `bind_context()`. |
| `secrets.py` | `SecretsManager` reads from env vars first, then Azure Key Vault. Converts kebab-case to `UPPER_SNAKE_CASE`. |

### `providers/` — Data Provider Adapters

- **`base.py`**: `BaseProvider` ABC. All providers implement `fetch_data()` and `fetch_instruments()` as async methods.
- **`tiingo.py`**: Market data (OHLCV, adjusted prices, corporate actions). Rate limit: 500 req/hr.
- **`fred.py`**: Macro time series from FRED. Rate limit: 120 req/min.
- **`registry.py`**: `ProviderRegistry` manages provider instances. Access via `get_provider_registry()`.

To add a new provider: subclass `BaseProvider`, implement abstract methods, register in `ProviderRegistry`.

### `storage/` — Database Layer

- **`database.py`**: `Database` class wraps SQLAlchemy engine. Connection string priority: explicit arg → env var → Key Vault → SQLite fallback. Access via `get_database()`.
- **`models.py`**: ORM models (star schema):
  - Dimensions: `DimSource`, `DimInstrument`, `DimMacroSeries`, `InstrumentTag`
  - Facts: `FactOHLCV`, `FactMacro`, `FactFeature`
  - Operational: `PipelineRun`
- **`repository.py`**: `BaseRepository[T]` with generic CRUD. Specialized repos: `InstrumentRepository`, `OHLCVRepository`, `FeatureRepository`, `PipelineRunRepository`, etc.

All fact tables use composite primary keys (e.g., `instrument_id + trade_date + feature_name`). Financial values use `Decimal(18, 6)`.

### `features/` — Feature Engineering

- **`base.py`**: `BaseFeature` ABC. Each feature defines `name`, `category`, `dependencies`, `lookback_days`, and `calculate()`.
- **`engine.py`** / **`engine_v2.py`**: `FeatureEngine` orchestrates calculation. Loads historical data, resolves dependencies, calculates in order (supports parallel), persists to `fact_feature`.
- **`registry.py`**: `FeatureRegistry` manages feature instances.
- **`schema.py`**: Feature schema definitions.
- **`transforms.py`**: Shared data transformations.
- **`diagnostics.py`**: Feature diagnostic utilities.

To add a new feature: subclass `BaseFeature`, implement `calculate()`, register in `FeatureRegistry`. Feature config lives in `config/features/registry.yaml`.

### `pipeline/` — Orchestration

- **`orchestrator.py`**: `PipelineOrchestrator.run(config)` is the main async entry point. Coordinates providers → validation → storage → features. Records each run in `pipeline_run` table.
  - `RunType`: `NIGHTLY`, `BACKFILL`, `MANUAL`
  - `RunStatus`: `RUNNING`, `SUCCESS`, `PARTIAL`, `FAILED`
- **`backfill.py`**: `BackfillManager` processes date ranges in configurable batches.

### `cli/` — Command Line Interface

Built with Typer. Entry point: `poetry run atlas`.

| Command | Description |
|---------|-------------|
| `atlas run` | Run pipeline for a target date |
| `atlas backfill --start --end` | Backfill historical data |
| `atlas status` | Show recent pipeline runs |
| `atlas init-db` | Initialize/reset database schema |
| `atlas instruments list` | List instruments |
| `atlas instruments add-tag` | Tag an instrument |
| `atlas instruments remove-tag` | Remove an instrument tag |
| `atlas dashboard` | Launch Streamlit dashboard |
| `atlas version` | Show version |

### `dashboard/` — Streamlit Web UI

- **`app.py`**: Multi-page Streamlit app. Pages: Overview, Price Data, Macro Data, Features, Pipeline Runs.
- **`auth.py`**: Username/password auth with session state. SHA256 hashing. Optional Azure AD integration (future).

---

## Configuration System

Configuration is layered (higher items take precedence):

1. Function arguments (explicit override)
2. Environment variables (`ATLAS_` prefix)
3. Azure Key Vault (production secrets)
4. `config/environments/{env}.yaml` (environment-specific overrides)
5. `config/default.yaml` (base config)
6. Pydantic model defaults

**Key environment variables** (see `.env.example`):

| Variable | Required | Description |
|----------|----------|-------------|
| `TIINGO_API_KEY` | Yes | Tiingo market data API key |
| `FRED_API_KEY` | Yes | FRED macro data API key |
| `ATLAS_DB_CONNECTION` | Yes | Database connection string |
| `ATLAS_ENV` | No | `development` or `production` |
| `ATLAS_KEYVAULT_URL` | No | Azure Key Vault URL |
| `ATLAS_LOG_LEVEL` | No | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `ATLAS_DASHBOARD_USERS` | No | JSON credentials for dashboard auth |
| `ATLAS_ALERT_EMAILS` | No | Comma-separated alert recipients |

Development uses SQLite (auto-fallback). Production uses Azure SQL (via connection string).

---

## Development Workflow

### Setup

```bash
# Install dependencies
poetry install

# Copy and configure environment
cp .env.example .env
# Edit .env with real API keys

# Initialize database
poetry run atlas init-db

# Run pipeline for today
poetry run atlas run

# Launch dashboard
poetry run atlas dashboard
```

### Code Quality Tools

| Tool | Purpose | Config |
|------|---------|--------|
| `ruff` | Linting + formatting | `pyproject.toml` `[tool.ruff]` |
| `mypy` | Static type checking | `pyproject.toml` `[tool.mypy]` |
| `pytest` | Testing | `pyproject.toml` `[tool.pytest.ini_options]` |
| `pre-commit` | Git hook enforcement | `.pre-commit-config.yaml` |

```bash
# Lint
poetry run ruff check src/

# Format
poetry run ruff format src/

# Type check
poetry run mypy src/atlas/

# Run tests
poetry run pytest

# Run tests with coverage
poetry run pytest --cov=atlas --cov-report=term-missing
```

### Testing Conventions

- Framework: `pytest` with `pytest-asyncio` (mode: `auto`)
- Test paths: `tests/` directory
- Coverage target: via `--cov=atlas`
- Async tests: use `async def test_*()` directly (asyncio_mode=auto)
- Mocking: `pytest-mock` (`mocker` fixture)
- Integration: `testcontainers` for container-based DB tests

---

## Key Conventions

### Python Style

- **Type hints**: Required everywhere (`disallow_untyped_defs = true` in mypy)
- **Line length**: 100 characters (Ruff)
- **Import order**: Managed by Ruff (isort rules)
- **Async**: All provider fetching and feature calculation is async; use `async/await`
- **Dataclasses**: Used for config and result objects (not Pydantic in most cases)
- **Enums**: Used for types, statuses, and categories

### Design Patterns

- **Singleton**: `get_settings()`, `get_database()`, `get_logger()` — use these functions, not direct instantiation
- **Registry**: `get_provider_registry()`, `FeatureRegistry` — register via registry, don't hard-code
- **Repository**: Always use repository classes to access DB; do not write raw SQL outside `repository.py`
- **ABC**: New providers must subclass `BaseProvider`; new features must subclass `BaseFeature`
- **Context managers**: Always use `with database.session() as session:` pattern for DB access

### Error Handling

- Raise specific `AtlasError` subclasses, not generic `Exception`
- Include `cause` attribute for chained exceptions
- Log errors via `structlog` before re-raising
- `PipelineOrchestrator` handles partial failures gracefully (sets status to `PARTIAL`)

### Database

- Never drop and recreate tables outside of `atlas init-db` or explicit migrations
- Use `repository.add_all()` for bulk inserts — it handles dialect-specific UPSERT
- Fact table composite keys must always be fully specified
- Financial values: use `Decimal(18, 6)` precision; avoid floats in DB columns
- Always filter by `is_active=True` on `dim_instrument` unless explicitly listing all

### Logging

```python
from atlas.core.logging import get_logger
logger = get_logger(__name__)

logger.info("message", key="value", count=n)     # structured fields
logger.error("error", error=str(e), ticker=sym)  # always include context
```

Use `bind_context()` to add persistent fields (e.g., `run_id`, `provider_name`) at the start of a pipeline step.

### Configuration

- Access config via `get_settings()` — never parse YAML manually
- Do not hardcode timeouts, limits, or thresholds; put them in `config/default.yaml`
- Feature parameters belong in `config/features/registry.yaml`
- FRED series belong in `config/providers/fred_series.yaml`

---

## Database Schema Summary

### Dimension Tables (Master Data)

| Table | Key Columns |
|-------|------------|
| `dim_source` | `source_id`, `name`, `provider_type`, `base_url` |
| `dim_instrument` | `instrument_id`, `ticker`, `name`, `exchange`, `asset_type`, `currency`, `sector`, `is_active` |
| `dim_macro_series` | `series_id`, `fred_id`, `name`, `category`, `frequency`, `units` |
| `instrument_tag` | `instrument_id`, `tag` (many-to-many) |

### Fact Tables (Observations)

| Table | Composite Key | Key Data Columns |
|-------|--------------|-----------------|
| `fact_ohlcv` | `instrument_id + trade_date` | `open`, `high`, `low`, `close`, `volume`, `adj_close`, `dividend`, `split_factor` |
| `fact_macro` | `series_id + obs_date` | `value` |
| `fact_feature` | `instrument_id + trade_date + feature_name` | `value`, `version` |

### Operational Tables

| Table | Key Columns |
|-------|------------|
| `pipeline_run` | `run_id`, `run_type`, `run_date`, `status`, `duration_seconds`, `records_inserted`, `records_updated`, `errors` |

---

## Azure Deployment

Infrastructure is defined as Bicep templates in `infrastructure/azure/`.

| Resource | Module | Purpose |
|----------|--------|---------|
| Azure SQL Database | `sql.bicep` | Primary data store |
| Azure Blob Storage | `storage.bicep` | Raw data archive (365-day retention) |
| Application Insights | `appinsights.bicep` | Structured log ingestion and monitoring |
| Azure Key Vault | `keyvault.bicep` | Secrets management |
| Azure Functions | `functionapp.bicep` | Nightly pipeline trigger (cron) + manual HTTP trigger |
| Azure Container Apps | `containerapp.bicep` | Streamlit dashboard hosting |

Deploy via:
```bash
bash infrastructure/azure/deploy.sh
```

Production pipeline runs as an Azure Function on a cron schedule (configured in `config/default.yaml` under `pipeline.schedule`).

---

## Feature Categories

Features are grouped into categories (defined in `config/features/registry.yaml`):

| Category | Examples |
|----------|---------|
| `returns` | `daily_return`, `log_return`, `cumulative_return_5d/21d/63d/126d` |
| `volatility` | Rolling volatility, beta, correlation |
| `momentum` | RSI, MACD, stochastic oscillator |
| `volume` | Volume ratios, on-balance volume |
| `relative` | Relative strength vs benchmark |
| `macro` | Macro-derived features (from FRED series) |

---

## FRED Macro Categories

Series are organized into three macro categories (defined in `config/providers/fred_series.yaml`):

| Category | Examples |
|----------|---------|
| `growth` | GDP, PAYEMS (payrolls), UNRATE, industrial production, retail sales, housing |
| `liquidity` | M1/M2 money supply, policy rates, Treasury yields, credit spreads |
| `risk_appetite` | VIX, equity indices, commodities, credit spreads, inflation expectations |

---

## Instrument Tagging System

Tags are defined in `config/instruments/tags.yaml`. Tag types:

- **Portfolio**: `portfolio_main`, `portfolio_alpha`, `portfolio_hedge`
- **Watchlist**: `watchlist_momentum`, `watchlist_value`, `watchlist_quality`
- **Sector** (auto-applied): `technology`, `healthcare`, `financials`, `energy`, `consumer`
- **Asset Type** (auto-applied): `etf`, `equity`
- **Market Cap**: `cap_large`, `cap_mid`, `cap_small`
- **Analysis**: `under_review`, `flagged`, `benchmark`

---

## Planned Extensions (Not Yet Implemented)

- Additional providers: EODHistoricalData, Polygon
- REST API layer (FastAPI)
- Backtesting module
- Portfolio optimization toolkit
- Data lake integration
- Full Azure AD authentication for dashboard

---

## Quick Reference: Adding New Components

### New Data Provider

1. Create `src/atlas/providers/{name}.py`
2. Subclass `BaseProvider` from `providers/base.py`
3. Implement `fetch_data()`, `fetch_instruments()`, and optionally `initialize()` / `close()`
4. Register in `ProviderRegistry` in `providers/registry.py`
5. Add rate limits and config to `config/default.yaml`

### New Feature

1. Create or extend a file in `src/atlas/features/`
2. Subclass `BaseFeature` from `features/base.py`
3. Implement `name`, `category`, `dependencies`, `lookback_days`, `calculate()`
4. Register in `FeatureRegistry` in `features/registry.py`
5. Add feature config entry in `config/features/registry.yaml`

### New CLI Command

1. Add a Typer command in `src/atlas/cli/main.py`
2. Use `get_settings()` for config access
3. Call orchestrator or relevant service — keep CLI thin

### New Dashboard Page

1. Add page logic in `src/atlas/dashboard/app.py`
2. Add navigation entry in the sidebar
3. Use `with database.session()` for DB queries
4. Keep queries read-only in the dashboard
