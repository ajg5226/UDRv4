# ATLAS V1 - Nightly Data Pipeline for Investment Management

ATLAS is a cloud-native data pipeline system designed for institutional investment management. It automates the collection, processing, and delivery of market data and macroeconomic indicators for quantitative analysis and decision-making.

## Features

- **Automated Nightly Pipeline** - Scheduled data collection from multiple providers
- **Multi-Provider Architecture** - Modular support for Tiingo, FRED, and future providers
- **Historical Backfill** - Load and process historical data for any date range
- **Feature Engineering** - Extensible framework for derived analytics
- **Portfolio Tagging** - Tag instruments for portfolio tracking and subset analysis
- **Macro Data Categorization** - FRED data organized by Growth, Liquidity, Risk Appetite
- **Streamlit Dashboard** - Web interface for data exploration and monitoring
- **Azure-Ready** - Infrastructure-as-code templates for Azure deployment

## Implementation Status (Code-Verified)

The sections below are verified against the current code in `src/atlas/`:

- **Primary entrypoint:** CLI commands in `src/atlas/cli/main.py` (`atlas run`, `atlas backfill`, `atlas status`, etc.).
- **Run scheduling:** `pipeline.schedule` exists in config, but in-repo execution is manual CLI driven; cron/timer wiring is external to this repo.
- **Provider persistence:** `PipelineOrchestrator` currently persists data only for providers named `tiingo` and `fred`.
- **Feature calculation in pipeline:** `PipelineOrchestrator._calculate_features()` is a placeholder; `FeatureEngineV2` exists but is not yet wired into `atlas run`.
- **Dashboard features page:** currently a placeholder ("coming soon"), not a query/view over `fact_feature`.
- **Instrument CLI actions:** `atlas instruments` supports `list`, `add-tag`, and `remove-tag`. `sync` is listed in help text but not implemented.

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
# Clone the repository
cd UDRv4

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

**Development default credentials (do not use in shared environments):**
- Username: `admin` or `analyst`
- Password: `atlas123`

`atlas dashboard` launches Streamlit using the relative path `src/atlas/dashboard/app.py`, so run it from the repository root.

### Operational Runbook

For day-2 operations, troubleshooting, and known pitfalls, see:

- [`docs/OPERATIONS_RUNBOOK.md`](docs/OPERATIONS_RUNBOOK.md)

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
│   │   ├── registry.py        # Legacy feature registry
│   │   ├── engine.py          # Legacy calculation engine
│   │   └── engine_v2.py       # Current feature engine implementation
│   ├── dashboard/             # Streamlit app
│   │   ├── app.py             # Main dashboard
│   │   └── auth.py            # Authentication
│   └── cli/                   # Command-line interface
│       └── main.py            # CLI commands
├── infrastructure/            # Infrastructure as code
│   └── azure/                 # Azure Bicep templates
├── docs/                      # Documentation
│   ├── ARCHITECTURE_DOCUMENT.md
│   └── OPERATIONS_RUNBOOK.md
├── tests/                     # Test suite
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
| `atlas dashboard` | Launch Streamlit dashboard |
| `atlas version` | Show version |

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
- **pipeline_run** - Pipeline execution history and status

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
4. Update `PipelineOrchestrator._persist_results()` so fetched records are actually written.

> Current implementation only has persistence branches for providers named `tiingo` and `fred`.

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

2. Register in `features/registry.py` (or `features/schema.py` for the V2 schema path)

> `FeatureEngineV2` is implemented in `src/atlas/features/engine_v2.py` but is not currently wired into `atlas run`.

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
| `ATLAS_DB_CONNECTION` | Database connection string | Yes |
| `ATLAS_ENV` | Environment (development/production) | No |
| `ATLAS_KEYVAULT_URL` | Azure Key Vault URL | For Azure |
| `ATLAS_DASHBOARD_USERS` | JSON user credentials | For production |

### Dashboard Credentials Format (`ATLAS_DASHBOARD_USERS`)

`ATLAS_DASHBOARD_USERS` must be JSON mapping usernames to **SHA-256 password hashes**.

Example:

```bash
python -c "import hashlib, json; print(json.dumps({'admin': hashlib.sha256('replace-me'.encode()).hexdigest()}))"
```

Then export the resulting JSON string:

```bash
export ATLAS_DASHBOARD_USERS='{"admin":"<sha256-hash>"}'
```

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
