# ATLAS V1 Architecture (Implementation Snapshot)

## Document info

| Field | Value |
|---|---|
| Version | 1.1.0 |
| Last updated | 2026-04-13 |
| Scope | Current codebase behavior (`src/atlas`) |

---

## 1. System intent

ATLAS ingests daily market data (Tiingo) and macro data (FRED), writes normalized records to a relational store, tracks operational runs, and exposes operational/data views through a CLI and Streamlit dashboard.

This document describes current implementation, not target-state design.

---

## 2. Runtime components and codepaths

### 2.1 CLI entrypoint

- `src/atlas/cli/main.py`
- Typer commands:
  - `atlas run`
  - `atlas backfill`
  - `atlas status`
  - `atlas init-db`
  - `atlas instruments`
  - `atlas dashboard`
  - `atlas version`

### 2.2 Orchestration

- `src/atlas/pipeline/orchestrator.py`
  - Initializes DB tables and providers
  - Creates `pipeline_run` record at start
  - Resolves providers and optional instrument/tag filters
  - Executes providers in parallel or sequential mode
  - Persists provider output to storage repositories
  - Marks run `success`, `partial`, or `failed`
- `src/atlas/pipeline/backfill.py`
  - Builds date list
  - Skips weekends by default
  - Batches date processing
  - Aggregates run-level stats and errors

### 2.3 Providers

- Base contract: `src/atlas/providers/base.py`
- Registry/bootstrap: `src/atlas/providers/registry.py`
- Implementations:
  - `src/atlas/providers/tiingo.py` (market data)
  - `src/atlas/providers/fred.py` (macro)

Provider key behaviors:
- API key lookup: env var first, then secrets manager lookup.
- Network retry: `tenacity` retry wrappers on timeout/network failures.
- Validation result attached to `ProviderResult`.

### 2.4 Storage layer

- Connection/session: `src/atlas/storage/database.py`
- Models: `src/atlas/storage/models.py`
- Repositories: `src/atlas/storage/repository.py`

The code uses repository-level upsert semantics for facts, keyed by natural composite keys.

### 2.5 Dashboard

- App: `src/atlas/dashboard/app.py`
- Auth: `src/atlas/dashboard/auth.py`

Views currently implemented:
- Overview
- Price Data
- Macro Data
- Features (placeholder text)
- Pipeline Runs

---

## 3. Pipeline execution flow

1. CLI creates `RunConfig` and calls `PipelineOrchestrator.run()`.
2. Orchestrator initializes dependencies (`create_tables()`, provider setup).
3. A `pipeline_run` row is inserted with `status='running'`.
4. Provider list is resolved from explicit args or `settings.pipeline.default_providers`.
5. Instrument scope is resolved:
   - explicit list, or
   - tickers matching any provided tag, or
   - all instruments/provider universe.
6. Providers fetch and validate data.
7. Orchestrator persists:
   - Tiingo -> `fact_ohlcv` (+ instrument/source dimensions)
   - FRED -> `fact_macro` (+ macro series/source dimensions)
8. Run record is completed with counts and errors.
9. CLI prints summary table.

Run status logic:
- `success`: all providers successful and no persistence errors
- `partial`: at least one provider succeeded or partially failed
- `failed`: no provider success

---

## 4. Data model summary (current tables)

Dimension tables:
- `dim_source`
- `dim_instrument`
- `dim_macro_series`

Fact tables:
- `fact_ohlcv`
- `fact_macro`
- `fact_feature`

Operational tables:
- `instrument_tag`
- `pipeline_run`
- `feature_diagnostic`

Important naming note:
- Runtime model names are singular (`pipeline_run`, `fact_feature`), not pluralized forms sometimes used in older docs.

---

## 5. Configuration and secrets

### 5.1 Configuration loading

`src/atlas/core/config.py` loads:
1. `config/default.yaml`
2. `config/environments/<ATLAS_ENV>.yaml`

Then pydantic settings can apply `ATLAS_*` environment values.

### 5.2 Secret lookup behavior

`src/atlas/core/secrets.py` lookup order:
1. Environment variable derived from secret name (`tiingo-api-key` -> `TIINGO_API_KEY`)
2. Azure Key Vault (if `ATLAS_KEYVAULT_URL` and credential are available)
3. Provided default

Database connection fallback:
- `ATLAS_DB_CONNECTION` env var
- Key Vault secret name in config (`atlas-db-connection`)
- fallback local SQLite: `sqlite:///atlas_dev.db`

---

## 6. Feature subsystem status

There are two feature engines in code:
- Legacy: `src/atlas/features/engine.py`
- New schema-driven: `src/atlas/features/engine_v2.py`

Current orchestrator behavior:
- `PipelineOrchestrator._calculate_features()` is a placeholder (`pass` with log message).
- Result: normal `atlas run` / backfill orchestration does not currently persist feature calculations.

Implication for operators:
- `fact_feature` population is not part of standard orchestrated runs yet.
- Feature catalog/schema code exists, but operational integration is incomplete.

---

## 7. Dashboard auth model

From `src/atlas/dashboard/auth.py`:
- Default dev users are built-in:
  - `admin` / `atlas123`
  - `analyst` / `atlas123`
- Password verification uses SHA-256 hashes.
- `ATLAS_DASHBOARD_USERS` can override users via JSON map of username -> hash.

---

## 8. Azure infrastructure mapping

IaC path:
- `infrastructure/azure/main.bicep`
- module templates under `infrastructure/azure/modules/`

Provisioned resources include:
- Key Vault
- Storage account
- SQL server + database
- Application Insights
- Function App
- Container App

Deployment helper:
- `infrastructure/azure/deploy.sh`

---

## 9. Operational runbook (code-backed)

### 9.1 Re-run failed date

```bash
atlas run --date 2026-04-10 --providers tiingo,fred --verbose
atlas status
```

### 9.2 Backfill date range

```bash
atlas backfill --start 2025-01-01 --end 2025-12-31 --batch-size 30
```

### 9.3 Dry-run estimate

```bash
atlas backfill --start 2025-01-01 --end 2025-12-31 --dry-run
```

### 9.4 Recover local schema

```bash
atlas init-db --force
```

---

## 10. Known gaps and risks

1. Feature stage is not integrated into orchestrator execution path.
2. Provider persistence branches are hard-coded by provider name (`tiingo`, `fred`), so adding providers requires orchestrator persistence extension.
3. Dashboard Features page is currently informational placeholder, not a live feature explorer.
4. Local execution depends on installing dependencies (`typer`, `pandas`, etc.); repo does not vendor a lockfile in this snapshot.
