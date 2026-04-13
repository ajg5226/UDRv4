# ATLAS V1

ATLAS is a data pipeline for ingesting market and macro data, persisting it to SQL/SQLite, and exposing operational visibility through a CLI and Streamlit dashboard.

This README is intentionally implementation-focused and reflects what the code currently does.

## What is currently implemented

- Providers: **Tiingo** (OHLCV) and **FRED** (macro series)
- Pipeline orchestration with run tracking in `pipeline_run`
- Backfill manager with date batching and weekend skipping
- Database repositories with idempotent upsert behavior
- Streamlit dashboard (overview, price, macro, features placeholder, run history)
- Azure IaC templates (`infrastructure/azure`)

### Important current constraint

Feature calculation is scaffolded in two engines (`features/engine.py` and `features/engine_v2.py`), but `PipelineOrchestrator._calculate_features()` is still a placeholder. Pipeline runs do not yet persist features from orchestrator execution.

## Quick start (local)

### Prerequisites

- Python 3.11+
- Poetry or pip
- Tiingo and FRED API keys

### Install

```bash
# from repository root
poetry install
# or
pip install -e .
```

### Configure secrets/env

```bash
export TIINGO_API_KEY="..."
export FRED_API_KEY="..."
export ATLAS_DB_CONNECTION="sqlite:///atlas_dev.db"
export ATLAS_ENV="development"
```

Secret resolution order in code:
1. Environment variable (for example `TIINGO_API_KEY`)
2. Azure Key Vault secret (if `ATLAS_KEYVAULT_URL` is configured)

If no DB connection is provided, the app falls back to `sqlite:///atlas_dev.db`.

### Initialize database

```bash
atlas init-db
```

## CLI workflow reference

### Run one date

```bash
# previous business day (Mon -> Fri, Sun -> Fri)
atlas run

# explicit date
atlas run --date 2026-04-10

# specific providers
atlas run --providers tiingo,fred

# only tagged instruments (matches ANY of the tags supplied)
atlas run --tags portfolio_main,watchlist

# skip feature stage
atlas run --skip-features
```

### Backfill

```bash
# estimate only
atlas backfill --start 2025-01-01 --end 2025-12-31 --dry-run

# execute (interactive confirm)
atlas backfill --start 2025-01-01 --end 2025-12-31 --batch-size 30
```

Backfill behavior from implementation:
- Skips weekends by default
- Processes dates in batches
- Continues after per-date failures unless configured otherwise in code
- Counts `partial` runs as successful in summary stats

### Status / instrument operations

```bash
atlas status
atlas instruments list
atlas instruments add-tag --ticker SPY --tag portfolio_main
atlas instruments remove-tag --ticker SPY --tag portfolio_main
```

### Dashboard

```bash
atlas dashboard
```

Default development credentials (from `src/atlas/dashboard/auth.py`):
- `admin` / `atlas123`
- `analyst` / `atlas123`

To override, set `ATLAS_DASHBOARD_USERS` to JSON mapping usernames to SHA-256 password hashes.

## Configuration model

Configuration is loaded from:
1. `config/default.yaml`
2. `config/environments/<ATLAS_ENV>.yaml` (deep-merged)
3. `ATLAS_*` environment variables (pydantic settings)

Key paths:
- `config/default.yaml`
- `config/environments/development.yaml`
- `config/environments/production.yaml`
- `config/providers/fred_series.yaml`

## Operational runbook snippets

### Recover a failed manual/nightly date

```bash
atlas run --date 2026-04-10 --providers tiingo,fred --verbose
atlas status
```

### Run tagged subset only

```bash
atlas run --date 2026-04-10 --tags portfolio_main
```

### Initialize clean local DB

```bash
atlas init-db --force
```

## Troubleshooting

| Symptom | Likely cause | What to check |
|---|---|---|
| `ModuleNotFoundError` when running `atlas` | Dependencies not installed | Re-run `poetry install` or `pip install -e .` |
| `Tiingo API key not configured` / `FRED API key not configured` | Missing env var and no Key Vault secret | Set `TIINGO_API_KEY` / `FRED_API_KEY` or configure Key Vault |
| `atlas run` succeeds but no records inserted | Provider returned empty data for that date/filter | Re-run with `--verbose`, check date, tags, and market calendar |
| `atlas status` shows DB disconnected | Bad `ATLAS_DB_CONNECTION` | Validate connection string or allow SQLite fallback |
| Dashboard login fails | `ATLAS_DASHBOARD_USERS` malformed | Ensure valid JSON with SHA-256 hashes |

## Azure deployment (infrastructure)

Infrastructure templates are under `infrastructure/azure`.

```bash
cd infrastructure/azure
export SQL_ADMIN_LOGIN="sqladmin"
export SQL_ADMIN_PASSWORD="..."
./deploy.sh
```

The script deploys:
- Key Vault
- Storage Account
- SQL Server + Database
- Application Insights
- Function App
- Container App

After deployment, populate Key Vault secrets:
- `tiingo-api-key`
- `fred-api-key`
- `atlas-db-connection`
