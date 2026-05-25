# Local Development Runbook

This runbook covers the source-backed local workflow for ATLAS developers:
configuration, database initialization, instrument bootstrap, validation, and
historical loading.

## Setup

Install the package with Poetry or pip:

```bash
poetry install
# or
pip install -e .
```

Copy the sample environment file and fill in provider keys:

```bash
cp .env.example .env
```

Required local values:

```env
TIINGO_API_KEY=your_tiingo_key
FRED_API_KEY=your_fred_key
ATLAS_DB_CONNECTION=sqlite:///atlas_dev.db
ATLAS_ENV=development
```

`ATLAS_ENV=development` loads `config/environments/development.yaml`, which:

- uses the SQLite database driver
- disables the raw archive
- switches logging to human-readable DEBUG output
- disables Application Insights

## Configuration loading

`atlas.core.config.get_settings()` loads:

1. `config/default.yaml`
2. `config/environments/<ATLAS_ENV>.yaml` when present
3. environment variables using the `ATLAS_` prefix and nested delimiter `__`

Example nested override:

```bash
export ATLAS_PIPELINE__DEFAULT_PROVIDERS='["tiingo"]'
```

Provider API keys are read by the provider/secrets layer from environment
variables during local development. In Azure, the settings file points at Key
Vault secret names.

## Initialize the local database

```bash
atlas init-db
```

Use `--force` only when you intentionally want to drop and recreate all tables:

```bash
atlas init-db --force
```

The SQLAlchemy models in `src/atlas/storage/models.py` are the current schema
source of truth. Important table names are singular:

- `instrument_tag`
- `pipeline_run`
- `fact_feature`
- `feature_diagnostic`

## Instrument universe bootstrap

The current local bootstrap path is `scripts/validate_local.py`, which reads
`ATLAS_INPUT_TEMPLATE_V1.csv` and inserts any missing tickers into
`dim_instrument` as ETFs.

Important constraints:

- The CSV must contain a `Ticker` column.
- Newly inserted instruments use `asset_type="etf"` and `tiingo_ticker=Ticker`.
- `config/default.yaml` references `config/instruments/universe.csv`, but that
  file is not currently present in the repository.
- `config/instruments/tags.yaml` defines tag metadata and `auto_apply` rules,
  but no code path currently applies those YAML rules automatically.
- The CLI supports `instruments list`, `instruments add-tag`, and
  `instruments remove-tag`. Although the CLI help mentions `sync`, there is no
  implemented sync action yet.

Manual tag examples:

```bash
atlas instruments list
atlas instruments add-tag --ticker SPY --tag benchmark
atlas instruments remove-tag --ticker SPY --tag benchmark
```

## Local validation

Run the validation script before relying on a local environment or before Azure
deployment work:

```bash
python3 scripts/validate_local.py
```

It performs these checks:

1. configuration loading
2. database creation and health check
3. instrument CSV load from `ATLAS_INPUT_TEMPLATE_V1.csv`
4. V2 feature schema and variant counts
5. provider initialization and FRED series config loading
6. feature generator calculations with synthetic OHLCV data
7. panel transform behavior
8. a mini pipeline object-construction check with real data fetches skipped

Provider validation initializes Tiingo and FRED, so missing API keys will be
reported as warnings or failures depending on which provider operation is reached.

## Running the pipeline locally

Run the previous business day:

```bash
atlas run
```

Run a specific date and provider set:

```bash
atlas run --date 2026-01-24 --providers tiingo,fred
```

Run against tagged instruments:

```bash
atlas run --tags portfolio_main
```

Make the current feature-stage limitation explicit:

```bash
atlas run --skip-features
```

Without `--skip-features`, the orchestrator reaches `_calculate_features`, but
that method currently logs a placeholder instead of invoking `FeatureEngineV2`.

## Backfills

Use the CLI for date-range backfills through the orchestrator:

```bash
atlas backfill --start 2020-01-01 --end 2026-01-24 --batch-size 30
```

Backfill behavior from `src/atlas/pipeline/backfill.py`:

- skips weekends by default
- processes date batches sequentially by default
- can continue after per-date failures
- reports aggregate inserted/updated counts and failed dates
- supports `--dry-run` for estimates without fetching data

There is also a standalone loader:

```bash
python3 scripts/backfill_5year.py
```

Use it for a direct five-year Tiingo/FRED load after instruments already exist in
the database. It bypasses the `atlas backfill` CLI flow and writes provider data
directly through repositories.

## Troubleshooting

- `ModuleNotFoundError` for pandas, streamlit, or rich:
  install dependencies with Poetry or `pip install -e .`.
- Provider initialization fails:
  confirm `TIINGO_API_KEY` and `FRED_API_KEY` are present in `.env` or the shell.
- No instruments are available:
  run `python3 scripts/validate_local.py` and confirm
  `ATLAS_INPUT_TEMPLATE_V1.csv` exists.
- Feature outputs are missing after `atlas run`:
  the orchestrator feature stage is currently a placeholder; use
  `FeatureEngineV2` directly for feature experiments.
- Tags from YAML are not applied:
  apply tags manually with `atlas instruments add-tag`; YAML `auto_apply` rules
  are metadata only today.
