# ATLAS V1 - Nightly Data Pipeline for Investment Management

ATLAS is a cloud-native data pipeline system designed for institutional investment management. It automates the collection, processing, and delivery of market data and macroeconomic indicators for quantitative analysis and decision-making.

## Features

- **Automated Nightly Pipeline** - Scheduled data collection from multiple providers
- **Multi-Provider Architecture** - Modular support for Tiingo, FRED, and future providers
- **Historical Backfill** - Load and process historical data for any date range
- **Feature Engineering** - Extensible framework for derived analytics (integration in progress)
- **Portfolio Tagging** - Tag instruments for portfolio tracking and subset analysis
- **Macro Data Categorization** - FRED data organized by Growth, Liquidity, Risk Appetite
- **Streamlit Dashboard** - Web interface for data exploration and monitoring
- **Azure-Ready** - Infrastructure-as-code templates for Azure deployment

## Current Implementation Status

The codebase includes both implemented workflows and planned/partial components. The list below reflects current behavior in `src/atlas`:

- `atlas run` / `atlas backfill` currently execute Tiingo and FRED ingestion, persist results, and write run metadata to `pipeline_run`.
- Feature generation modules exist in `src/atlas/features/`, but orchestrator feature calculation is still a placeholder (`PipelineOrchestrator._calculate_features`).
- `atlas instruments` supports `list`, `add-tag`, and `remove-tag`; `sync` is listed in help text but is not implemented.
- Database schema setup is currently done with `atlas init-db` (`Base.metadata.create_all`), not Alembic migrations.

## Quick Start

### Prerequisites

- Python 3.11+
- Poetry (recommended) or pip
- Azure CLI (for cloud deployment)
- API keys for:
  - [Tiingo](https://www.tiingo.com/) (market data)
  - [FRED](https://fred.stlouisfed.org/) (macro data)

### Installation

```bash
# Clone the repository and enter the repo root
cd <repo-root>

# Install dependencies with Poetry
poetry install

# Or with pip
pip install -e .
```

### Configuration

1. **Set environment variables** (for local development):

```bash
export TIINGO_API_KEY="your_tiingo_key"
export FRED_API_KEY="your_fred_key"
export ATLAS_DB_CONNECTION="sqlite:///atlas_dev.db"  # Or your SQL connection string
```

2. **Or use a `.env` file**:

```env
TIINGO_API_KEY=your_tiingo_key
FRED_API_KEY=your_fred_key
ATLAS_DB_CONNECTION=sqlite:///atlas_dev.db
```

### Initialize the Database

```bash
atlas init-db
```

### Run the Pipeline

```bash
# Run for the previous business day
atlas run

# Run for a specific date
atlas run --date 2026-01-24

# Run specific providers only
atlas run --providers tiingo,fred

# Run for instruments with specific tags
atlas run --tags portfolio_main
```

### Backfill Historical Data

```bash
# Backfill a date range
atlas backfill --start 2020-01-01 --end 2026-01-24

# Dry run to see what would be processed
atlas backfill --start 2020-01-01 --end 2026-01-24 --dry-run
```

### Launch the Dashboard

```bash
atlas dashboard
```

Then open http://localhost:8501 in your browser.

**Default credentials:**
- Username: `admin` or `analyst`
- Password: `atlas123`

## Project Structure

```
<repo-root>/
├── config/                     # Configuration files
│   ├── default.yaml           # Main configuration
│   ├── providers/             # Provider-specific configs
│   │   └── fred_series.yaml   # FRED series definitions
│   ├── instruments/           # Instrument configs
│   │   └── tags.yaml          # Tag definitions
│   └── features/              # Feature configs
│       └── registry.yaml      # Feature definitions
├── src/atlas/                  # Main package
│   ├── core/                  # Core utilities
│   │   ├── config.py          # Configuration management
│   │   ├── logging.py         # Structured logging
│   │   ├── exceptions.py      # Custom exceptions
│   │   └── secrets.py         # Secrets management
│   ├── providers/             # Data providers
│   │   ├── base.py            # Base provider class
│   │   ├── registry.py        # Provider registry
│   │   ├── tiingo.py          # Tiingo provider
│   │   └── fred.py            # FRED provider
│   ├── pipeline/              # Pipeline orchestration
│   │   ├── orchestrator.py    # Main orchestrator
│   │   └── backfill.py        # Backfill management
│   ├── storage/               # Database layer
│   │   ├── models.py          # SQLAlchemy models
│   │   ├── database.py        # Connection management
│   │   └── repository.py      # Data access layer
│   ├── features/              # Feature engineering
│   │   ├── base.py            # Legacy base feature class
│   │   ├── schema.py          # V2 feature catalog/schema
│   │   ├── generators.py      # Family-specific generators
│   │   ├── transforms.py      # Cross-sectional transforms
│   │   ├── engine.py          # Legacy calculation engine
│   │   └── engine_v2.py       # V2 calculation engine
│   ├── dashboard/             # Streamlit app
│   │   ├── app.py             # Main dashboard
│   │   └── auth.py            # Authentication
│   └── cli/                   # Command-line interface
│       └── main.py            # CLI commands
├── scripts/                   # Local validation / utility scripts
│   ├── validate_local.py
│   └── backfill_5year.py
├── infrastructure/            # Infrastructure as code
│   └── azure/                 # Azure Bicep templates
├── docs/                      # Documentation
│   └── ARCHITECTURE_DOCUMENT.md
├── pyproject.toml             # Project configuration
└── README.md                  # This file
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `atlas run` | Execute single-date pipeline run |
| `atlas backfill` | Run historical backfill with batching |
| `atlas status` | Show database health and latest run |
| `atlas init-db` | Create schema (`--force` drops/recreates) |
| `atlas instruments list` | List active instruments |
| `atlas instruments add-tag` | Add tag to instrument |
| `atlas instruments remove-tag` | Remove tag from instrument |
| `atlas instruments sync` | Reserved in CLI help; not implemented yet |
| `atlas dashboard` | Launch Streamlit dashboard (run from repo root) |
| `atlas version` | Show version |

## Operational Runbook (Local)

### 1) Bootstrap a local environment

```bash
poetry install
cp .env.example .env
```

Set at least:

- `TIINGO_API_KEY`
- `FRED_API_KEY`
- `ATLAS_DB_CONNECTION` (optional; defaults to local SQLite if unset)

### 2) Initialize schema

```bash
atlas init-db
```

Use `atlas init-db --force` only when you intentionally want to drop all tables.

### 3) Validate local wiring before long runs

```bash
python scripts/validate_local.py
```

This script checks config loading, provider initialization, database schema, feature modules, and mini pipeline object creation.

### 4) Run ingestion workflows

```bash
# Single date
atlas run --date 2026-01-24 --providers tiingo,fred

# Historical range
atlas backfill --start 2026-01-01 --end 2026-01-24 --batch-size 10
```

`atlas backfill` prompts for confirmation unless `--dry-run` is used.

### 5) Launch dashboard

```bash
atlas dashboard
```

The CLI launches `src/atlas/dashboard/app.py` via a relative path, so run this command from the repository root.

### 6) Optional bulk historical bootstrap script

```bash
python scripts/backfill_5year.py
```

This script performs a long-form provider backfill loop and writes data incrementally; review its source before using in shared environments.

## Database Schema

### Dimension Tables

- **dim_source** - Data provider metadata
- **dim_instrument** - Instrument master (tickers, exchanges, types)
- **dim_macro_series** - FRED series metadata with categories

### Fact Tables

- **fact_ohlcv** - Daily OHLCV price data (raw + adjusted)
- **fact_macro** - Macroeconomic indicator observations
- **fact_feature** - Calculated feature values

### Operational Tables

- **instrument_tag** - Many-to-many instrument tags
- **pipeline_run** - Pipeline execution history

## Adding New Providers

1. Create a new provider class inheriting from `BaseProvider`:

```python
from atlas.providers.base import BaseProvider, ProviderType, ProviderResult

class MyProvider(BaseProvider):
    @property
    def name(self) -> str:
        return "my_provider"
    
    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.MARKET_DATA
    
    async def fetch_data(self, target_date, instruments=None) -> ProviderResult:
        # Implementation
        ...
    
    async def fetch_instruments(self) -> list[InstrumentInfo]:
        # Implementation
        ...
    
    def validate(self, data) -> ValidationResult:
        # Implementation
        ...
```

2. Register in `providers/registry.py`
3. Add configuration in `config/default.yaml`

## Adding New Features

ATLAS currently has two feature tracks:

- Legacy interface (`BaseFeature` + registry in `features/registry.py`)
- V2 schema/generator/transform workflow (`features/schema.py`, `features/generators.py`, `features/transforms.py`, `features/engine_v2.py`)

`PipelineOrchestrator` does not yet invoke feature engines automatically. If you add feature definitions, validate them with `scripts/validate_local.py` and your own execution scripts.

Example legacy feature class:

```python
from atlas.features.base import BaseFeature

class MyFeature(BaseFeature):
    @property
    def name(self) -> str:
        return "my_feature"
    
    @property
    def category(self) -> str:
        return "custom"
    
    @property
    def dependencies(self) -> list[str]:
        return ["adj_close"]  # Required input data
    
    @property
    def lookback_days(self) -> int:
        return 20
    
    def calculate(self, data, target_date, parameters=None):
        # Implementation
        ...
```

2. Register in `features/registry.py` (legacy path), or in `config/features/registry.yaml` + V2 schema paths depending on your workflow.

## Azure Deployment

### Prerequisites

- Azure CLI installed and logged in
- Azure subscription

### Deploy Infrastructure

```bash
cd infrastructure/azure

# Set environment variables
export SQL_ADMIN_LOGIN="sqladmin"
export SQL_ADMIN_PASSWORD="your_secure_password"

# Deploy
./deploy.sh
```

### Post-Deployment

1. Add secrets to Key Vault:
   - `tiingo-api-key`
   - `fred-api-key`
   - `atlas-db-connection`

2. Deploy application code to Function App

3. Deploy dashboard container to Container Apps

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `TIINGO_API_KEY` | Tiingo API key | Yes |
| `FRED_API_KEY` | FRED API key | Yes |
| `ATLAS_DB_CONNECTION` | Database connection string | No (defaults to local SQLite) |
| `ATLAS_ENV` | Environment (development/production) | No |
| `ATLAS_KEYVAULT_URL` | Azure Key Vault URL | For Azure |
| `ATLAS_DASHBOARD_USERS` | JSON user credentials | For production |

## FRED Data Categories

ATLAS organizes ~100 FRED series into three categories:

### Growth
- GDP and output metrics
- Employment data
- Consumer activity
- Housing indicators
- Business surveys (PMI)

### Liquidity
- Money supply (M1, M2)
- Federal Reserve balance sheet
- Policy rates
- Treasury yields
- Yield curve spreads

### Risk Appetite
- Volatility (VIX)
- Credit spreads
- Equity indices
- Commodities
- Inflation expectations

## Development

### Running Tests

```bash
pytest
```

`pyproject.toml` is configured for a `tests/` testpath, but this repository snapshot does not currently include committed test files.

### Code Quality

```bash
# Linting
ruff check src/

# Type checking
mypy src/atlas/
```

### Pre-commit Hooks

```bash
pre-commit install
pre-commit run --all-files
```

## Troubleshooting and Common Pitfalls

### `atlas dashboard` fails with missing app path

- Run the command from repo root.
- The CLI currently calls Streamlit with `src/atlas/dashboard/app.py` as a relative path.

### Provider failures due to missing keys

- Ensure `TIINGO_API_KEY` and `FRED_API_KEY` are set (or available via Key Vault secret names configured in `config/default.yaml`).
- You can quickly verify provider setup using `python scripts/validate_local.py`.

### Unexpected SQLite usage

- If `ATLAS_DB_CONNECTION` is not set and no Key Vault value is available, ATLAS falls back to `sqlite:///atlas_dev.db`.
- Confirm DB target with `atlas status` and your environment configuration.

### Backfill prompts in automation

- `atlas backfill` asks for confirmation interactively.
- Use `--dry-run` first to inspect scope, then run interactively for actual execution.

## Roadmap

### V1.1
- Additional providers (EODHistoricalData, Polygon)
- Enhanced dashboard visualizations
- Azure AD SSO integration

### V1.2
- REST API layer (FastAPI)
- Advanced alerting
- Feature versioning

### V2.0
- Backtesting module
- Portfolio optimization toolkit
- Data lake integration

## License

Proprietary - Internal Use Only

## Support

For questions or issues, contact the ATLAS team.
