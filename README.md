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

# Poetry (recommended for app/CLI entrypoints)
poetry install

# Or pip (includes scipy used by Feature Engine V2)
pip install -r requirements.txt
pip install -e .
```

`scipy` is imported by Feature Engine V2 (`generators`, `transforms`, `diagnostics`) and is listed in `requirements.txt`, but it is **not** currently declared in `pyproject.toml`. After `poetry install` alone, install scipy before calling `calculate_features()`:

```bash
poetry run pip install 'scipy>=1.11'
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
# (374 tickers, including SPY and the V2 factor/sector ETFs). All rows are
# inserted as asset_type="etf". Tags are not applied automatically.

# 3) Optional: bulk 5-year history helper (loads .env; not the same as atlas backfill)
#    Prefer `atlas backfill` for FRED/macro history — see Troubleshooting.
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

`atlas run` records `run_type=manual`. The cron expression in `config/default.yaml` is not executed by any checked-in scheduler. Default `--date` is the previous weekday (Monday → Friday, Sunday → Friday). There is no holiday calendar.

**Instrument scope:** the CLI has no `--instruments` flag. `_get_instruments()` uses a ticker list only when `--tags` is set; otherwise it passes `None` to Tiingo, which then downloads the entire `/tiingo/daily` universe and fetches each ticker sequentially (config `rate_limit_per_hour: 500`). Seed instruments, tag the subset you want, and run with `--tags`:

```bash
atlas instruments add-tag --ticker SPY --tag portfolio_main
atlas run --date 2026-01-24 --tags portfolio_main
```

An empty tag match returns `[]` (no Tiingo calls), not the full universe. Missing tickers seen during persist are inserted as `asset_type="equity"`.

### Backfill Historical Data

```bash
atlas backfill --start 2020-01-01 --end 2026-01-24
atlas backfill --start 2020-01-01 --end 2026-01-24 --dry-run
atlas backfill --start 2020-01-01 --end 2026-01-24 --batch-size 10 --skip-features
```

Non-dry-run backfills print an estimate and require interactive confirmation (`Proceed with backfill?`). `BackfillConfig` defaults to `skip_weekends=True` and `skip_holidays=False` (no holiday calendar is implemented). `resume_from` and `parallel_batches` exist on the dataclass but are not exposed by the CLI.

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

Roles are defined in code but not enforced on dashboard pages after login. There is no production fail-closed guard today: production still falls back to these defaults if `ATLAS_DASHBOARD_USERS` is missing. `dashboard.auth.method: azure_ad` is config-only; only simple username/password is implemented.

Sidebar pages: **Overview** (counts + latest 10 runs), **Price Data** (OHLCV chart/table + CSV download), **Macro Data** (FRED category filter/chart), **Features** (V1 stub — not `FEATURE_CATALOG`), **Pipeline Runs** (filterable run history).

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
- Dashboard Features page is a stub: it lists a hard-coded V1 feature subset and incorrectly states that features are calculated as part of the pipeline

### V2 catalog (source of truth: `FEATURE_CATALOG`)

36 enabled base features expand to **139** name variants (lookback × transform). Default `FeatureEngineConfig.max_priority=3` includes all current priorities.

| Family | Base features |
|--------|----------------|
| Momentum | `mom_ts`, `mom_risk_adj`, `mom_intermediate`, `mom_residual` |
| Trend | `trend_slope`, `trend_adx`, `trend_efficiency`, `trend_choppiness` |
| Breakout | `breakout_high`, `breakout_dist_high`, `breakout_dist_low` |
| Mean reversion | `mr_zscore`, `mr_reversal`, `mr_dip_in_uptrend`, `mr_rsi` |
| Factor | `factor_beta_mom`, `factor_beta_qual`, `factor_beta_lowvol`, `factor_beta_value`, `factor_beta_size`, `factor_beta_spy`, `factor_tilt_score` |
| Risk | `risk_realized_vol`, `risk_idio_vol`, `risk_beta_trend`, `risk_drawdown`, `risk_downside_vol` |
| UDR | `udr_up_capture`, `udr_down_capture`, `udr_capture_asymmetry`, `udr_capture_delta` |
| Regime | `regime_hurst`, `regime_variance_ratio`, `regime_vol_level`, `regime_corr_dispersion`, `regime_corr_spy` |

Transforms: `raw`, `rank`, `zscore` (plus `quintile`/`decile` where defined). Benchmark/factor loaders look up `SPY` and `FACTOR_ETF_CONFIG` tickers (`MTUM`, `QUAL`, `USMV`, `VLUE`, `IWM`, plus sector ETFs) in `dim_instrument`; missing tickers skip those families rather than failing the run. Diagnostics (`feature_diagnostic`) are always deferred today (`_calculate_and_store_diagnostics` is a no-op).

### Standalone usage (after OHLCV history exists)

```python
import asyncio
from datetime import date
from atlas.features import calculate_features, FeatureEngineConfig, FeatureFamily

async def main():
    result = await calculate_features(
        target_date=date(2026, 1, 24),
        config=FeatureEngineConfig(
            max_priority=3,
            apply_transforms=True,
            calculate_diagnostics=True,  # currently deferred in the engine
            enabled_families=list(FeatureFamily),
            batch_size=50,
        ),
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
# Optional deploy-script overrides (read only by deploy.sh, not the Python app):
export ATLAS_RESOURCE_GROUP=atlas-rg   # default
export ATLAS_LOCATION=eastus           # default
export ATLAS_ENV=dev                   # Bicep environment: dev|staging|prod (default dev)
./deploy.sh
```

`ATLAS_ENV` is overloaded: the Python config loader defaults to `development` and reads `config/environments/{ATLAS_ENV}.yaml`. `deploy.sh` defaults to `dev` and passes that string to Bicep (`atlas-dev-*` resource names). There is no `config/environments/dev.yaml`. After a deploy, reset `ATLAS_ENV=development` (or `production`) before running `atlas` commands.

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
| `ATLAS_ENV` | Config loader **and** `deploy.sh` | No | App: `development`/`production` YAML overlays. Deploy script: Bicep `dev`/`staging`/`prod` (default `dev`). Do not leave `ATLAS_ENV=dev` set when running the CLI. |
| `ATLAS_RESOURCE_GROUP` | `deploy.sh` only | No | Default `atlas-rg` |
| `ATLAS_LOCATION` | `deploy.sh` only | No | Default `eastus` |
| `ATLAS_KEYVAULT_URL` | Secrets manager | Azure | Vault URL |
| `ATLAS_DASHBOARD_USERS` | Dashboard auth | Recommended outside local use | JSON `{"user":"<sha256 hex>"}`; unset → default users |

`ATLAS_LOG_LEVEL` and `ATLAS_ALERT_EMAILS` appear in `.env.example` as documentation stubs; application code reads logging/notification settings from YAML config, and no email sender is implemented.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `atlas` ignores `.env` | CLI does not load dotenv | `source .env` (or export vars) before running |
| Dashboard file-not-found | Wrong CWD | Run `atlas dashboard` from repo root |
| Empty instrument list | Universe not loaded | Run `python3 scripts/validate_local.py` (loads `ATLAS_INPUT_TEMPLATE_V1.csv`) or insert instruments |
| `atlas run` takes hours / hits Tiingo 429 | No `--tags` → `instruments is None` → full `/tiingo/daily` universe, one HTTP call per ticker | Seed CSV, `atlas instruments add-tag`, then `atlas run --tags <tag>`. CLI has no `--instruments` |
| `--tags` run fetches nothing | Tag has no matching rows | `atlas instruments add-tag --ticker X --tag Y` first; empty tag match is `[]`, not "all" |
| Holiday gap after default `atlas run` | Previous-weekday helper only; `BackfillConfig.skip_holidays` is `False` | Pass `--date` for the last US session; do not expect holiday skipping |
| Re-ingest wiped prices | `OHLCVRepository.upsert_batch` assigns every incoming field, including `None`/NaN | Avoid sparse provider rows on re-run; no preserve-existing-value path today |
| Zero prices/macro disappear in dashboard | `get_as_dataframe` uses truthiness (`if r.open else None`) | Treat `0` as missing in readback until that path is fixed |
| `ATLAS_ENV=dev` then CLI misses overlays | Deploy script value ≠ config filename (`development.yaml`) | Use `development`/`production` for the app; `dev`/`staging`/`prod` only for `deploy.sh` |
| Features table empty after `atlas run` | Placeholder feature hook | Call `FeatureEngineV2` / `calculate_features` directly; pipeline wiring pending |
| `instruments sync` fails | Unimplemented action | Use `list` / `add-tag` / `remove-tag` only |
| Production dashboard uses `atlas123` | Auth fails open to defaults | Set valid `ATLAS_DASHBOARD_USERS` JSON hashes |
| `poetry run atlas ... --help` metavar error | Typer/Click help rendering issue in some installs | Inspect CLI source/`--help` alternatives; commands still run |
| `ModuleNotFoundError: scipy` after Poetry install | `scipy` missing from `pyproject.toml` | `poetry run pip install 'scipy>=1.11'` or use `requirements.txt` |
| Tags from `config/instruments/tags.yaml` not applied | Config path is stored but not loaded by app code | Tag via `atlas instruments add-tag` or seed through `validate_local.py` |
| Expected `config/instruments/universe.csv` missing | File is referenced in config only; not present | Use `ATLAS_INPUT_TEMPLATE_V1.csv` via `validate_local.py` |
| `development.yaml` sets `parallel_providers: false` but providers still run concurrently | CLI/`BackfillManager` build `RunConfig` without mapping `settings.pipeline.parallel_providers`; `RunConfig.parallel` defaults to `True` | Expect parallel provider execution unless you construct `RunConfig(parallel=False)` in code |
| `scripts/backfill_5year.py` writes OHLCV but little/no FRED data | Helper reads `row.get("date")` while `FredProvider.fetch_date_range` returns `obs_date` | Prefer `atlas backfill --providers fred` for macro history until the helper is fixed |
| Dashboard Features page shows outdated names | Stub in `dashboard/app.py` hard-codes a V1 subset and claims pipeline calculation | Use `FEATURE_CATALOG` / `calculate_features()`; do not treat the page as catalog source of truth |

## Configuration Notes

These YAML keys are parsed into settings but **not consumed** by runtime codepaths today:

| Config key | File | Reality |
|------------|------|---------|
| `features.registry_config` | `config/features/registry.yaml` | Not read by V1 or V2 feature engines |
| `instruments.universe_csv` | `config/instruments/universe.csv` | Path only; file absent; no loader |
| `instruments.tags_config` | `config/instruments/tags.yaml` | Path only; tags are managed in DB via CLI |
| `pipeline.parallel_providers` | `default.yaml` / env overlays | Settings field only; orchestrator uses `RunConfig.parallel` (default `True`) |
| `logging.app_insights` | `default.yaml` | No OpenCensus/App Insights exporter wired in `setup_logging` |
| `storage.raw_archive` / `notifications` | `default.yaml` | Config-only; no Blob writer or email sender |
| `BackfillConfig.skip_holidays` / `resume_from` / `parallel_batches` | `backfill.py` | Dataclass fields only; CLI does not expose them. Holidays are never skipped. |

## Development

```bash
python3 scripts/validate_local.py   # preferred local smoke check
ruff check src/
mypy src/atlas/
```

A full `tests/` suite, `.pre-commit-config.yaml`, and Alembic migration tree are not present on `main` in this tree. `pytest` / pre-commit / Alembic remain declared dependencies or target workflow until those assets land. Schema creation today is `atlas init-db` (SQLAlchemy `create_all`).

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
