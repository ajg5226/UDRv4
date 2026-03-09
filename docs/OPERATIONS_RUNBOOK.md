# ATLAS Operations Runbook (Current Implementation)

Last verified: 2026-03-09

This runbook documents how to operate the ATLAS code currently in this repository (not the full target architecture).

## 1) Preconditions

- Python 3.11+
- Installed dependencies (`poetry install` or `pip install -e .`)
- API keys:
  - `TIINGO_API_KEY`
  - `FRED_API_KEY`
- Optional database connection:
  - `ATLAS_DB_CONNECTION` (defaults to `sqlite:///atlas_dev.db` if unset)

## 2) Local Setup

```bash
# from repo root
cp .env.example .env

# set real API keys in .env or environment
# TIINGO_API_KEY=...
# FRED_API_KEY=...

atlas init-db
atlas status
```

## 3) Core Workflows

### A. Single-day pipeline run

```bash
# default target date = previous business day
atlas run

# explicit date + provider filter
atlas run --date 2026-01-24 --providers tiingo,fred

# restrict market-data instruments to tagged subset
atlas run --date 2026-01-24 --tags portfolio_main
```

What this does:
- Initializes DB tables if needed.
- Runs configured providers (parallel when multiple providers are selected).
- Upserts:
  - `fact_ohlcv` from Tiingo data
  - `fact_macro` from FRED data
- Updates `pipeline_run` metadata.

### B. Backfill run

```bash
# preview scope only
atlas backfill --start 2025-01-01 --end 2025-03-31 --dry-run

# execute (interactive confirmation required)
atlas backfill --start 2025-01-01 --end 2025-03-31 --batch-size 30
```

Notes:
- Weekend dates are skipped by default.
- Backfill uses one pipeline run per date.
- `atlas backfill` prompts for confirmation; it is not fully non-interactive.

### C. Instrument tag management

```bash
atlas instruments list
atlas instruments add-tag --ticker SPY --tag portfolio_main
atlas instruments remove-tag --ticker SPY --tag portfolio_main
```

Notes:
- The CLI help text mentions `sync`, but `sync` is not implemented in current command logic.

### D. Dashboard

```bash
atlas dashboard
```

- URL: `http://localhost:8501`
- Default dev credentials:
  - `admin` / `atlas123`
  - `analyst` / `atlas123`
- Production should set `ATLAS_DASHBOARD_USERS` (`{"user":"sha256_hash"}`).

## 4) Feature Pipeline Reality Check

- `atlas run` and `atlas backfill` currently do **not** execute full feature calculation.
- `PipelineOrchestrator._calculate_features` is a placeholder.
- Feature schema and V2 engine modules are present (`atlas.features.*`) for manual/programmatic usage, but not wired into orchestration.

## 5) Troubleshooting

| Symptom | Likely cause | Resolution |
|---|---|---|
| `Tiingo API key not configured` | Missing `TIINGO_API_KEY` and no Key Vault secret | Export `TIINGO_API_KEY` or configure Key Vault (`ATLAS_KEYVAULT_URL`) |
| `FRED API key not configured` | Missing `FRED_API_KEY` and no Key Vault secret | Export `FRED_API_KEY` or configure Key Vault |
| `Database: Disconnected` in `atlas status` | Bad `ATLAS_DB_CONNECTION` or driver mismatch | Start with SQLite default, then validate SQL connection string/ODBC driver |
| Backfill waits for input in automation | Interactive confirmation prompt | Use `--dry-run` for automation checks, execute full run only in interactive session |
| Dashboard login fails | Wrong credentials format in `ATLAS_DASHBOARD_USERS` | Provide valid JSON map of `username -> sha256(password)` |
| Features page shows no computed features | Current dashboard page is placeholder | This is expected in current implementation |

## 6) Useful Validation Script

```bash
python3 scripts/validate_local.py
```

This script checks config, DB schema, provider initialization, and feature module wiring with synthetic data.
