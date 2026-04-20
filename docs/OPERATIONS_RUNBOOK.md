# ATLAS Operations Runbook

## Purpose

This runbook covers day-to-day operation of the ATLAS pipeline and dashboard using the current implementation under `src/atlas/`.

It is intended for engineers who run or troubleshoot:

- `atlas run` / `atlas backfill`
- provider ingestion (Tiingo, FRED)
- dashboard access and data visibility
- pipeline run status in the database

## Scope (Implementation-Verified)

The following behaviors are verified in code:

- Pipeline entrypoint is CLI (`src/atlas/cli/main.py`).
- Runtime orchestration is `PipelineOrchestrator` (`src/atlas/pipeline/orchestrator.py`).
- Backfill is `BackfillManager` (`src/atlas/pipeline/backfill.py`).
- Data persistence in orchestrator is currently hard-coded for providers named `tiingo` and `fred`.
- Feature calculation inside orchestrator is currently a placeholder (`_calculate_features` logs and returns).
- Dashboard authentication uses `ATLAS_DASHBOARD_USERS` and SHA-256 hash comparison (`src/atlas/dashboard/auth.py`).

## 1) Pre-flight Checklist

1. Ensure required env vars are set:
   - `TIINGO_API_KEY`
   - `FRED_API_KEY`
   - `ATLAS_DB_CONNECTION` (optional for local; defaults to SQLite if unset)
2. Confirm you are in repo root before launching dashboard.
3. Initialize schema if first run:

```bash
atlas init-db
```

## 2) Environment and Secrets

### Local development defaults

- If `ATLAS_DB_CONNECTION` is not set, the app falls back to `sqlite:///atlas_dev.db`.
- Dashboard auth defaults to users `admin` and `analyst` with password `atlas123` when `ATLAS_DASHBOARD_USERS` is unset.

### Dashboard credentials format

`ATLAS_DASHBOARD_USERS` must be JSON of `username -> sha256(password)`.

Example (single user):

```bash
python -c "import hashlib, json; print(json.dumps({'admin': hashlib.sha256('change-me'.encode()).hexdigest()}))"
export ATLAS_DASHBOARD_USERS='{"admin":"<sha256-hash>"}'
```

## 3) Core Operational Workflows

### Run a single-date pipeline

```bash
# Previous business day
atlas run

# Specific date
atlas run --date 2026-01-24

# Specific providers
atlas run --providers tiingo,fred

# Tag-filtered instruments (market data providers)
atlas run --tags portfolio_main

# Skip feature phase (currently equivalent to default behavior)
atlas run --skip-features
```

Operational notes:

- Default date is previous business day (Monday resolves to prior Friday).
- Provider execution is parallel when multiple providers are selected.
- Run metadata is written to `pipeline_run`.

### Backfill historical data

```bash
# Preview only
atlas backfill --start 2020-01-01 --end 2020-01-31 --dry-run

# Execute
atlas backfill --start 2020-01-01 --end 2020-01-31
```

Operational notes:

- CLI backfill prompts for confirmation.
- Weekends are skipped by default in `BackfillConfig`.
- Dates are batched (`--batch-size`, default 30).
- Parallel backfill workers exist in code (`parallel_batches`) but are not exposed as a CLI flag.

### Check pipeline state

```bash
atlas status
```

This checks DB connectivity and prints latest pipeline run metadata.

## 4) Dashboard Operations

### Launch

```bash
atlas dashboard
```

Constraints:

- Must be run from repository root because it launches `src/atlas/dashboard/app.py` via a relative path.
- If auth is enabled and session is unauthenticated, login page is shown first.

### Current dashboard pages

- Overview: recent run and top-level counts
- Price Data: OHLCV query and chart
- Macro Data: FRED-series query and chart
- Features: placeholder page (not backed by runtime feature pipeline integration yet)
- Pipeline Runs: recent runs and run details

## 5) Troubleshooting

### Symptom: `atlas run` fails with provider auth errors

Likely causes:

- missing `TIINGO_API_KEY` or `FRED_API_KEY`
- wrong API key values

What to check:

1. env vars are present in current shell
2. provider-specific connectivity from your environment

### Symptom: run status is `partial`

Meaning:

- at least one provider succeeded and at least one failed, or persistence had provider-level errors

What to check:

1. `pipeline_run.errors`
2. provider logs for failed instruments/series
3. whether selected providers are registered and enabled in config

### Symptom: no feature records after successful run

Current behavior:

- expected from orchestrator path today; feature phase is a placeholder in `PipelineOrchestrator._calculate_features`.

### Symptom: dashboard login fails for configured users

Likely cause:

- `ATLAS_DASHBOARD_USERS` values are plain text, not SHA-256 hashes.

### Symptom: custom provider fetches but data is not persisted

Likely cause:

- orchestrator persistence currently branches only on provider names `tiingo` and `fred`.

Action:

- extend `_persist_results` in `src/atlas/pipeline/orchestrator.py` to handle new provider outputs.

## 6) Common Pitfalls and Constraints

- `atlas instruments sync` is listed in CLI argument help but not implemented.
- FeatureEngineV2 exists (`src/atlas/features/engine_v2.py`) but is not wired into the main orchestrator run path.
- Raw response archiving to blob storage is configured in settings but not implemented in orchestrator/provider persistence flow.
- Database table names are singular in code: `fact_feature`, `pipeline_run`.

## 7) Change Runbook for Extensibility

### Adding a new provider safely

1. Implement `BaseProvider`.
2. Register in `setup_providers()` (`src/atlas/providers/registry.py`).
3. Add config under `config/default.yaml`.
4. Update orchestrator persistence (`_persist_results`) for provider-specific record mapping and writes.
5. Validate with a single-date `atlas run --providers <name>`.

### Enabling real feature calculation in pipeline path

1. Wire `PipelineOrchestrator._calculate_features()` to call `FeatureEngineV2.calculate`.
2. Ensure instrument scope uses `instrument_id` values (not tickers) for feature engine calls.
3. Validate writes into `fact_feature`.
4. Update dashboard Features page to query and display persisted features.

## 8) Minimal Incident Triage Checklist

When a scheduled or manual run fails:

1. Check `atlas status`.
2. Inspect latest `pipeline_run` status and `errors`.
3. Identify failing provider(s) and whether failure is auth, rate limit, or schema-related.
4. Re-run targeted command (`atlas run --date <date> --providers <provider>`).
5. Confirm persistence row counts (inserted/updated) and run completion status.
