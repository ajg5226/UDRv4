# ATLAS Developer Runbook

This runbook documents the **current, code-verified workflows** for local development and operations.

## Scope and Source of Truth

Verified against these codepaths:

- CLI: `src/atlas/cli/main.py`
- Orchestration: `src/atlas/pipeline/orchestrator.py`, `src/atlas/pipeline/backfill.py`
- Providers: `src/atlas/providers/tiingo.py`, `src/atlas/providers/fred.py`
- Storage: `src/atlas/storage/database.py`, `src/atlas/storage/models.py`, `src/atlas/storage/repository.py`
- Dashboard: `src/atlas/dashboard/app.py`, `src/atlas/dashboard/auth.py`
- Config + secrets: `src/atlas/core/config.py`, `src/atlas/core/secrets.py`, `config/default.yaml`

## 1) Local Setup

### Prerequisites

- Python 3.11
- Tiingo API key
- FRED API key

### Install

```bash
# Option A: Poetry
poetry install
poetry run atlas version

# Option B: pip
python3 -m pip install -e .
atlas version
```

### Required environment variables

```bash
export TIINGO_API_KEY="<your-key>"
export FRED_API_KEY="<your-key>"
```

Optional:

```bash
# If omitted, ATLAS falls back to sqlite:///atlas_dev.db
export ATLAS_DB_CONNECTION="sqlite:///atlas_dev.db"

# Select environment overrides from config/environments/{env}.yaml
export ATLAS_ENV="development"
```

## 2) First-Time Bootstrap

```bash
atlas init-db
atlas status
```

What this does:

- Creates database schema (table names from models, including `pipeline_run`, `fact_ohlcv`, `fact_macro`, `fact_feature`)
- Confirms database connectivity and displays latest run metadata

## 3) Core Workflows

### A. Single-day pipeline run

```bash
# Previous business day
atlas run

# Specific date
atlas run --date 2026-01-24

# Restrict providers
atlas run --providers tiingo,fred

# Restrict universe by tags
atlas run --tags portfolio_main
```

Operational notes:

- `run` mode in CLI uses `RunType.MANUAL`.
- If no `--date`, it defaults to previous business day.
- If no instrument filter is provided, Tiingo can fetch a very large universe.

### B. Historical backfill

```bash
# Estimate without executing
atlas backfill --start 2020-01-01 --end 2020-03-31 --dry-run

# Execute
atlas backfill --start 2020-01-01 --end 2020-03-31
```

Backfill behavior:

- Skips weekends by default
- Processes by date batches
- Prompts for interactive confirmation before execution
- Continues on per-date errors by default

### C. Instrument/tag operations

```bash
atlas instruments list
atlas instruments add-tag --ticker SPY --tag portfolio_main
atlas instruments remove-tag --ticker SPY --tag portfolio_main
```

Constraint:

- `atlas instruments` help text mentions `sync`, but `sync` is not implemented in the action handler.

### D. Dashboard

```bash
atlas dashboard
```

Then open `http://localhost:8501`.

Default local credentials:

- `admin` / `atlas123`
- `analyst` / `atlas123`

To override users:

- Set `ATLAS_DASHBOARD_USERS` to JSON mapping usernames to SHA-256 hashes.

## 4) Troubleshooting

### `ModuleNotFoundError` for CLI dependencies

Install dependencies (`poetry install` or `python3 -m pip install -e .`) before running commands.

### Runs are too slow or fetch too much data

Scope the run using:

- `--providers` (for example, `fred` only)
- `--tags` (small instrument subset)

### Backfill automation hangs

`atlas backfill` is interactive and asks for confirmation. Use `--dry-run` to plan and handle confirmation in your automation wrapper.

### Dashboard custom users cannot log in

`ATLAS_DASHBOARD_USERS` requires SHA-256 hashes, not plain-text passwords.

### Feature values expected but not showing up

Current orchestrator path has a feature-calculation placeholder (`_calculate_features`) and does not yet persist feature values during `atlas run` / `atlas backfill`.

## 5) Known Gaps (Current State)

- Pipeline feature step is not wired to `FeatureEngine`/`FeatureEngineV2` in the orchestrator run path.
- Dashboard "Features" page is currently informational only.
- Automated tests are not yet committed under `tests/`.
