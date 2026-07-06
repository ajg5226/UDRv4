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

For local validation with SQLite, use the checked-in harness:

```bash
export ATLAS_ENV=development
export ATLAS_DB_CONNECTION="sqlite:///atlas_dev.db"
python scripts/validate_local.py
```

The validation script creates the schema, loads instruments from
`ATLAS_INPUT_TEMPLATE_V1.csv`, validates the Feature Engine V2 schema and
generators with sample data, and confirms the pipeline objects can be created
without making external API calls.

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

# Skip the feature calculation hook
atlas run --skip-features
```

**Current feature status:** `atlas run` and `atlas backfill` expose a
`--skip-features` flag, but the orchestrator's feature-calculation hook is
currently a placeholder. Use the standalone Feature Engine V2 API described
below when you need to calculate and persist feature rows.

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

Dashboard authentication is login-only in the current app. The `admin` and
`analyst` users can access the same dashboard pages; page-level RBAC is a
planned production hardening step.

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
│       └── registry.yaml      # Legacy feature registry; V2 uses src/atlas/features/schema.py
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
│   │   ├── schema.py          # V2 feature catalog
│   │   ├── generators.py      # V2 family calculators
│   │   ├── transforms.py      # Cross-sectional transforms
│   │   ├── engine_v2.py       # V2 calculation engine
│   │   └── engine.py          # Legacy calculation engine
│   ├── dashboard/             # Streamlit app
│   │   ├── app.py             # Main dashboard
│   │   └── auth.py            # Authentication
│   └── cli/                   # Command-line interface
│       └── main.py            # CLI commands
├── infrastructure/            # Infrastructure as code
│   └── azure/                 # Azure Bicep templates
├── docs/                      # Documentation
│   └── ARCHITECTURE_DOCUMENT.md
├── scripts/                   # Local validation and backfill helpers
├── ATLAS_INPUT_TEMPLATE_V1.csv # Local instrument bootstrap CSV
├── ATLAS_V1_PRD.md            # Product requirements
├── pyproject.toml             # Project configuration
└── README.md                  # This file
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `atlas run [--date YYYY-MM-DD] [--providers tiingo,fred] [--tags tag] [--skip-features]` | Execute pipeline for a date |
| `atlas backfill --start YYYY-MM-DD --end YYYY-MM-DD [--batch-size 30] [--dry-run] [--skip-features]` | Run historical backfill |
| `atlas status` | Show pipeline status |
| `atlas init-db` | Initialize database schema |
| `atlas instruments list` | List active instruments |
| `atlas instruments add-tag` | Add tag to instrument |
| `atlas instruments remove-tag` | Remove tag from instrument |
| `atlas dashboard` | Launch Streamlit dashboard |
| `atlas version` | Show version |

The CLI help mentions `atlas instruments sync`, but that action is not
implemented yet and returns `Unknown action: sync`.

## Database Schema

The physical SQLAlchemy table names are singular. Use these names for direct
SQL, migrations, and troubleshooting.

### Dimension Tables

- **dim_source** - Data provider metadata
- **dim_instrument** - Instrument master (tickers, exchanges, types)
- **dim_macro_series** - FRED series metadata with categories

### Fact Tables

- **fact_ohlcv** - Daily OHLCV price data (raw + adjusted)
- **fact_macro** - Macroeconomic indicator observations
- **fact_feature** - Calculated feature values with versioning and lineage
- **feature_diagnostic** - Feature quality metrics such as IC and hit rate

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

Feature Engine V2 is driven by `src/atlas/features/schema.py`, not by
`config/features/registry.yaml`. The schema module is the source of truth for
feature names, families, lookbacks, transforms, data requirements, priority, and
version metadata.

1. Add a `FeatureDefinition` to `FEATURE_CATALOG` with `register_feature()`:

```python
from atlas.features.schema import (
    DataRequirement,
    Directionality,
    FeatureDefinition,
    FeatureFamily,
    HorizonFamily,
    TransformType,
    register_feature,
)

register_feature(FeatureDefinition(
    name="my_signal",
    family=FeatureFamily.MOMENTUM,
    description="Example signal based on adjusted close history",
    horizon_family=HorizonFamily.MEDIUM,
    lookback_days=63,
    min_history=126,
    transforms=[TransformType.RAW, TransformType.RANK, TransformType.ZSCORE],
    requires=[DataRequirement.OHLCV],
    directionality=Directionality.HIGHER_BETTER,
    priority=2,
))
```

2. Implement or extend the matching family generator in
   `src/atlas/features/generators.py`.
3. Validate with `python scripts/validate_local.py`, which exercises the schema,
   generators, and transforms with sample data.
4. For standalone calculation, call the V2 engine:

```python
import asyncio
from datetime import date

from atlas.features.engine_v2 import calculate_features

result = asyncio.run(calculate_features(date(2026, 1, 24)))
print(result.records_written, result.errors)
```

Feature variants are generated from lookback and transform settings. For
example, a base feature named `mom_ts` with a 21-day lookback and rank transform
is stored as `mom_ts_21d_rank` in `fact_feature`.

The legacy `BaseFeature`, `FeatureRegistry`, and `FeatureEngine` modules remain
in the package for compatibility, but new production features should use Feature
Engine V2.

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
