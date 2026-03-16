# ATLAS V1 - Nightly Data Pipeline for Investment Management

ATLAS is a cloud-native data pipeline system designed for institutional investment management. It automates the collection, processing, and delivery of market data and macroeconomic indicators for quantitative analysis and decision-making.

## Implementation Status (Verified from Current Code)

This repository contains both production-ready ingestion paths and in-progress analytics components.

- Implemented and wired in CLI/orchestrator:
  - Tiingo OHLCV ingestion
  - FRED macro ingestion
  - Manual runs, backfills, run-status tracking
  - Streamlit dashboard for overview, price, macro, and run history
- Present but not yet wired into the pipeline run path:
  - Feature calculation in `atlas.pipeline.orchestrator._calculate_features` (currently a placeholder)
  - Dashboard "Features" page (currently informational placeholder)
- Developer workflow and operations runbook: [`docs/DEVELOPER_RUNBOOK.md`](docs/DEVELOPER_RUNBOOK.md)

## Features

- **Automated Nightly Pipeline** - Scheduled data collection from multiple providers
- **Multi-Provider Architecture** - Modular support for Tiingo, FRED, and future providers
- **Historical Backfill** - Load and process historical data for any date range
- **Feature Engineering** - Extensible framework for derived analytics
- **Portfolio Tagging** - Tag instruments for portfolio tracking and subset analysis
- **Macro Data Categorization** - FRED data organized by Growth, Liquidity, Risk Appetite
- **Streamlit Dashboard** - Web interface for data exploration and monitoring
- **Azure-Ready** - Infrastructure-as-code templates for Azure deployment

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
# From repository root
cd /path/to/UDRv4

# Install dependencies with Poetry
poetry install
poetry run atlas version

# Or with pip
python3 -m pip install -e .
# Optional after pip install:
atlas version
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
UDRv4/
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
│   │   ├── base.py            # Base feature class
│   │   ├── registry.py        # Feature registry
│   │   ├── engine.py          # Legacy feature engine
│   │   ├── engine_v2.py       # Enhanced feature engine (not wired by orchestrator yet)
│   │   └── schema.py          # Unified feature schema/catalog
│   ├── dashboard/             # Streamlit app
│   │   ├── app.py             # Main dashboard
│   │   └── auth.py            # Authentication
│   └── cli/                   # Command-line interface
│       └── main.py            # CLI commands
├── infrastructure/            # Infrastructure as code
│   └── azure/                 # Azure Bicep templates
├── docs/                      # Documentation
│   ├── ARCHITECTURE_DOCUMENT.md
│   └── DEVELOPER_RUNBOOK.md
├── scripts/                   # Local validation and utility scripts
├── pyproject.toml             # Project configuration
└── README.md                  # This file
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `atlas run` | Execute pipeline for a date |
| `atlas backfill` | Run historical backfill |
| `atlas status` | Show pipeline status |
| `atlas init-db` | Initialize database schema |
| `atlas instruments list` | List active instruments |
| `atlas instruments add-tag` | Add tag to instrument |
| `atlas instruments remove-tag` | Remove tag from instrument |
| `atlas dashboard` | Launch Streamlit dashboard |
| `atlas version` | Show version |

> Note: `atlas instruments` help text includes `sync`, but `sync` is not currently implemented in `src/atlas/cli/main.py`.

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

1. Create a feature class inheriting from `BaseFeature`:

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

2. Register in `features/registry.py`

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
| `ATLAS_DB_CONNECTION` | Database connection string | No (falls back to local SQLite) |
| `ATLAS_ENV` | Environment (development/production) | No |
| `ATLAS_KEYVAULT_URL` | Azure Key Vault URL | For Azure |
| `ATLAS_DASHBOARD_USERS` | JSON map of username -> SHA-256 password hash | For custom dashboard users |

Example for custom dashboard users:

```bash
# Generate hash for password "my_password"
python3 - <<'PY'
import hashlib
print(hashlib.sha256("my_password".encode()).hexdigest())
PY

export ATLAS_DASHBOARD_USERS='{"admin":"<sha256-hash>","analyst":"<sha256-hash>"}'
```

## Common Pitfalls and Troubleshooting

- **`ModuleNotFoundError` when running `atlas` commands**
  - Install dependencies first (`poetry install` or `python3 -m pip install -e .`).
- **Run is very slow or appears stalled**
  - `atlas run` without `--tags` can fetch a very large Tiingo universe.
  - Start with scoped runs (for example, `atlas run --providers fred` or `atlas run --tags portfolio_main`).
- **`atlas backfill` stops for confirmation in scripts/automation**
  - `atlas backfill` is interactive by default and prompts `Proceed with backfill?`.
  - Use `--dry-run` for planning, or drive interactive confirmation explicitly in automation.
- **Dashboard login works locally but not with custom users**
  - `ATLAS_DASHBOARD_USERS` expects SHA-256 hashes, not plain-text passwords.
- **Database connection errors in local development**
  - If `ATLAS_DB_CONNECTION` is not set, ATLAS falls back to `sqlite:///atlas_dev.db`.
  - Run `atlas init-db` before the first run to ensure schema exists.
- **Expecting engineered features in pipeline output**
  - Current orchestrator path logs a feature-calculation placeholder and does not persist computed features yet.

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

Current state: there are no committed automated tests under `tests/` yet; use CLI smoke runs and the local validator while tests are being built out:

```bash
python3 scripts/validate_local.py
```

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
