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
│   │   └── engine.py          # Calculation engine
│   ├── dashboard/             # Streamlit app
│   │   ├── app.py             # Main dashboard
│   │   └── auth.py            # Authentication
│   └── cli/                   # Command-line interface
│       └── main.py            # CLI commands
├── infrastructure/            # Infrastructure as code
│   └── azure/                 # Azure Bicep templates
├── docs/                      # Documentation
│   └── ARCHITECTURE_DOCUMENT.md
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
| `atlas instruments remove-tag` | Remove tag from instrument |
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
| `ATLAS_DB_CONNECTION` | Database connection string | Yes |
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

## Implementation Notes and Operational Runbook

This section reflects current implementation in `src/atlas/*` and is intended to avoid drift between architecture intent and runtime behavior.

### Current implementation snapshot

- Providers currently wired into the orchestrator: `tiingo`, `fred` (`src/atlas/providers/registry.py`).
- Pipeline defaults to previous business day if `--date` is omitted (`RunConfig._get_previous_business_day`).
- Core persistence path implemented for:
  - Tiingo -> `fact_ohlcv`
  - FRED -> `fact_macro`
  - Run metadata -> `pipeline_run`
- `atlas instruments` supports `list`, `add-tag`, and `remove-tag`.
- Feature calculation is not yet integrated into the main orchestrator persistence path (the orchestrator method currently logs a placeholder in `src/atlas/pipeline/orchestrator.py`).

### Common workflows

#### 1) First-time local setup

```bash
# 1. Install dependencies
poetry install

# 2. Export required API keys
export TIINGO_API_KEY="..."
export FRED_API_KEY="..."

# 3. Optional: force local SQLite for development
export ATLAS_DB_CONNECTION="sqlite:///atlas_dev.db"

# 4. Create schema
atlas init-db
```

#### 2) Daily/manual run

```bash
# Previous business day
atlas run

# Explicit date and provider subset
atlas run --date 2026-01-24 --providers tiingo,fred

# Restrict to tagged instruments
atlas run --tags portfolio_main
```

#### 3) Backfill workflow

```bash
# Preview work without executing
atlas backfill --start 2020-01-01 --end 2020-03-31 --dry-run

# Execute backfill
atlas backfill --start 2020-01-01 --end 2020-03-31
```

Notes:
- Backfill skips weekends by default.
- CLI prompts for confirmation before execution unless `--dry-run` is used.

#### 4) Tagging instruments for scoped runs

```bash
# Inspect active instruments
atlas instruments list

# Add/remove tags
atlas instruments add-tag --ticker AAPL --tag portfolio_main
atlas instruments remove-tag --ticker AAPL --tag portfolio_main
```

### Troubleshooting and pitfalls

- **`atlas status` shows database disconnected**
  - Verify `ATLAS_DB_CONNECTION`.
  - If unset, ATLAS falls back to local SQLite (`sqlite:///atlas_dev.db`).
  - Run `atlas init-db` after changing connection targets.

- **Provider authentication errors**
  - `Tiingo API key not configured` -> set `TIINGO_API_KEY` (or Key Vault secret `tiingo-api-key`).
  - `FRED API key not configured` -> set `FRED_API_KEY` (or Key Vault secret `fred-api-key`).

- **Runs return little/no market data**
  - Weekend/holiday dates can produce sparse or empty market records.
  - Use an explicit business date when validating ingestion behavior.

- **Backfills are slower than expected**
  - Tiingo and FRED ingestion currently fetch per ticker/series; wide universes increase request count.
  - Use `--providers` and `--tags` to scope runs during debugging.

- **Dashboard login confusion in local development**
  - Default users are `admin` / `analyst`.
  - Default password is `atlas123`.
  - Override via `ATLAS_DASHBOARD_USERS` (JSON map of username -> password hash).

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
