# ATLAS V1 - Nightly Data Pipeline for Investment Management

ATLAS is a data pipeline for institutional investment management. The checked-in runtime is **CLI-driven**: ingest market and macro data, backfill history, store results in SQL, and explore them in a Streamlit dashboard. Azure infrastructure and scheduler settings describe the target operating model; this repository does not yet ship a timer-triggered Function host.

## Features

- **CLI-Driven Pipeline** - Manual single-date runs; cron config is present for future scheduling
- **Multi-Provider Architecture** - Tiingo (OHLCV) and FRED (macro), with a pluggable provider registry
- **Historical Backfill** - Date-range backfills via CLI, plus a dedicated 5-year helper script
- **Feature Engineering (V2 library)** - Catalog, generators, and transforms exist; pipeline persistence is not wired yet
- **Portfolio Tagging** - Tag instruments and filter pipeline runs by tag
- **Macro Categorization** - FRED series grouped as Growth, Liquidity, Risk Appetite
- **Streamlit Dashboard** - Login-gated exploration of prices, macro, and run status
- **Azure-Ready IaC** - Bicep templates under `infrastructure/azure/`

## Quick Start

### Prerequisites

- Python 3.11+
- Poetry (recommended) or pip
- Azure CLI (only for cloud deployment)
- API keys for [Tiingo](https://www.tiingo.com/) and [FRED](https://fred.stlouisfed.org/)

### Installation

```bash
cd UDRv4
poetry install
# or: pip install -e .
```

### Configuration

Export variables in the shell for CLI and dashboard commands:

```bash
export TIINGO_API_KEY="your_tiingo_key"
export FRED_API_KEY="your_fred_key"
export ATLAS_DB_CONNECTION="sqlite:///atlas_dev.db"
export ATLAS_ENV=development
```

`.env` is loaded automatically by `scripts/validate_local.py` and `scripts/backfill_5year.py` only. The `atlas` CLI and dashboard do **not** call `load_dotenv()`. If you keep secrets in `.env`, export them first:

```bash
set -a
source .env
set +a
```

If `ATLAS_DB_CONNECTION` is unset and Key Vault is unavailable, storage falls back to `sqlite:///atlas_dev.db`.

### Bootstrap Local Data

```bash
# 1) Create schema
atlas init-db

# 2) Validate config, schema, providers, and feature catalog (loads .env)
python3 scripts/validate_local.py
# validate_local also loads instruments from ATLAS_INPUT_TEMPLATE_V1.csv

# 3) Optional: bulk 5-year history helper (loads .env; not the same as atlas backfill)
python3 scripts/backfill_5year.py

# 4) Or run a single date / ranged CLI backfill
atlas run --date 2026-01-24
atlas backfill --start 2020-01-01 --end 2026-01-24
```

### Run the Pipeline

```bash
atlas run                                 # previous business day
atlas run --date 2026-01-24
atlas run --providers tiingo,fred
atlas run --tags portfolio_main
atlas run --skip-features                 # skip the placeholder feature hook
atlas run -v                              # DEBUG logging
```

`atlas run` records `run_type=manual`. The cron expression in `config/default.yaml` is not executed by any checked-in scheduler.

### Backfill Historical Data

```bash
atlas backfill --start 2020-01-01 --end 2026-01-24
atlas backfill --start 2020-01-01 --end 2026-01-24 --dry-run
atlas backfill --start 2020-01-01 --end 2026-01-24 --batch-size 10 --skip-features
```

Non-dry-run backfills print an estimate and require interactive confirmation (`Proceed with backfill?`).

### Launch the Dashboard

Run from the repository root (the CLI launches `src/atlas/dashboard/app.py` as a relative path):

```bash
atlas dashboard
```

Open http://localhost:8501.

**Default credentials** (used when `ATLAS_DASHBOARD_USERS` is unset or invalid JSON):

| Username | Password |
|----------|----------|
| `admin`  | `atlas123` |
| `analyst`| `atlas123` |

Roles are defined in code but not enforced on dashboard pages after login. There is no production fail-closed guard today: production still falls back to these defaults if `ATLAS_DASHBOARD_USERS` is missing.

## Project Structure

```
UDRv4/
├── config/
│   ├── default.yaml
│   ├── environments/          # development.yaml, production.yaml
│   ├── providers/fred_series.yaml
│   ├── instruments/tags.yaml
│   └── features/registry.yaml # legacy/unused by Feature Engine V2
├── src/atlas/
│   ├── core/                  # config, logging, secrets, exceptions
│   ├── providers/             # Tiingo, FRED, registry
│   ├── pipeline/              # orchestrator, backfill
│   ├── storage/               # models, database, repository
│   ├── features/              # schema (FEATURE_CATALOG), engine_v2, generators, transforms
│   ├── dashboard/             # Streamlit app + auth
│   └── cli/main.py            # atlas CLI
├── scripts/
│   ├── validate_local.py
│   └── backfill_5year.py
├── infrastructure/azure/      # Bicep + deploy.sh
├── docs/ARCHITECTURE_DOCUMENT.md
├── ATLAS_INPUT_TEMPLATE_V1.csv
└── README.md
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `atlas run` | Execute pipeline for one date (`--date`, `--providers`, `--tags`, `--skip-features`, `-v`) |
| `atlas backfill` | Historical backfill (`--start/--end` required; `--batch-size`, `--dry-run`, `--skip-features`, `-v`) |
| `atlas status` | DB health + latest `pipeline_run` |
| `atlas init-db [--force]` | Create schema; `--force` drops tables after confirmation |
| `atlas instruments list` | List active instruments (first 50 shown) |
| `atlas instruments add-tag --ticker X --tag Y` | Add tag |
| `atlas instruments remove-tag --ticker X --tag Y` | Remove tag |
| `atlas dashboard` | Launch Streamlit (repo-root CWD) |
| `atlas version` | Print version |

`instruments sync` appears in the CLI help text but is **not implemented**.

## Database Schema

Exact ORM table names from `src/atlas/storage/models.py`:

| Table | Purpose |
|-------|---------|
| `dim_source` | Provider metadata |
| `dim_instrument` | Instrument master |
| `dim_macro_series` | FRED series metadata |
| `fact_ohlcv` | Daily OHLCV (raw + adjusted) |
| `fact_macro` | Macro observations |
| `fact_feature` | Engineered features (table exists; pipeline does not populate it yet) |
| `feature_diagnostic` | Feature quality metrics (IC/hit rate); engine diagnostics persistence is deferred |
| `instrument_tag` | Instrument ↔ tag mapping |
| `pipeline_run` | Run history |

## Feature Engineering

### What is implemented

- **Source of truth:** `FEATURE_CATALOG` in `src/atlas/features/schema.py`
- **Engine:** `FeatureEngineV2` / `calculate_features()` in `src/atlas/features/engine_v2.py`
- **Supporting modules:** generators, panel transforms, diagnostics helpers
- **Legacy V1:** `FeatureEngine` + `FeatureRegistry` remain for compatibility; they do not read `config/features/registry.yaml`

### What is not wired

- `PipelineOrchestrator._calculate_features()` only logs a placeholder
- Normal `atlas run` / `atlas backfill` do not write `fact_feature`
- Dashboard Features page is a stub

### Standalone usage (after OHLCV history exists)

```python
import asyncio
from datetime import date
from atlas.features import calculate_features, FeatureEngineConfig

async def main():
    result = await calculate_features(
        target_date=date(2026, 1, 24),
        config=FeatureEngineConfig(max_priority=3, apply_transforms=True),
    )
    print(result.features_calculated, result.records_written, result.errors)

asyncio.run(main())
```

To extend the V2 catalog, register definitions in `src/atlas/features/schema.py` (not `registry.yaml`). Wire the orchestrator to `FeatureEngineV2` before expecting nightly feature persistence.

## Adding New Providers

1. Subclass `BaseProvider` in `src/atlas/providers/`
2. Register in `src/atlas/providers/registry.py`
3. Add provider config under `config/default.yaml` / env overlays

## Azure Deployment

```bash
cd infrastructure/azure
export SQL_ADMIN_LOGIN="sqladmin"
export SQL_ADMIN_PASSWORD="your_secure_password"
./deploy.sh
```

Post-deploy:

1. Store secrets in Key Vault: `tiingo-api-key`, `fred-api-key`, `atlas-db-connection`
2. Add an application entrypoint before relying on Function App scheduling (no timer host is checked in)
3. Deploy the dashboard container to Container Apps
4. Run ingestion via `atlas run` / `atlas backfill` until a scheduler is wired

## Environment Variables

| Variable | Used by | Required | Notes |
|----------|---------|----------|-------|
| `TIINGO_API_KEY` | Tiingo provider | Yes for market fetch | Falls back to Key Vault secret `tiingo-api-key` |
| `FRED_API_KEY` | FRED provider | Yes for macro fetch | Falls back to Key Vault secret `fred-api-key` |
| `ATLAS_DB_CONNECTION` | Storage | Recommended | Else Key Vault, else SQLite |
| `ATLAS_ENV` | Config loader | No | Selects `config/environments/{env}.yaml` (default `development`) |
| `ATLAS_KEYVAULT_URL` | Secrets manager | Azure | Vault URL |
| `ATLAS_DASHBOARD_USERS` | Dashboard auth | Recommended outside local use | JSON `{"user":"<sha256 hex>"}`; unset → default users |

`ATLAS_LOG_LEVEL` and `ATLAS_ALERT_EMAILS` appear in `.env.example` as documentation stubs; application code reads logging/notification settings from YAML config, and no email sender is implemented.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `atlas` ignores `.env` | CLI does not load dotenv | `source .env` (or export vars) before running |
| Dashboard file-not-found | Wrong CWD | Run `atlas dashboard` from repo root |
| Empty instrument list | Universe not loaded | Run `python3 scripts/validate_local.py` (loads `ATLAS_INPUT_TEMPLATE_V1.csv`) or insert instruments |
| Features table empty after `atlas run` | Placeholder feature hook | Call `FeatureEngineV2` / `calculate_features` directly; pipeline wiring pending |
| `instruments sync` fails | Unimplemented action | Use `list` / `add-tag` / `remove-tag` only |
| Production dashboard uses `atlas123` | Auth fails open to defaults | Set valid `ATLAS_DASHBOARD_USERS` JSON hashes |
| `poetry run atlas ... --help` metavar error | Typer/Click help rendering issue in some installs | Inspect CLI source/`--help` alternatives; commands still run |

## Development

```bash
python3 scripts/validate_local.py   # preferred local smoke check
ruff check src/
mypy src/atlas/
```

A full `tests/` suite is not present on `main` in this tree; treat `pytest` / pre-commit as target workflow until tests land.

## Roadmap

### Near-term integration
- Wire orchestrator to `FeatureEngineV2`
- Azure Functions timer entrypoint
- Raw archive writer + notification sender
- Dashboard RBAC enforcement / production fail-closed auth

### Later
- Additional providers, FastAPI layer, Azure AD SSO, backtesting toolkit

## License

Proprietary - Internal Use Only

## Support

For questions or issues, contact the ATLAS team.
