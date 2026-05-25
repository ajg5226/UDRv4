# ATLAS V1 Nightly Data Pipeline – Product Requirements Document (PRD)

## Executive Summary
The ATLAS V1 Nightly Data Pipeline is a **cloud-based data ingestion and processing system** designed to run automatically each night. Its primary purpose is to **collect data from multiple external sources**, integrate and transform that data, and store it in a centralized database for easy access. By the next morning, users will have a **unified, up-to-date dataset** available through a streamlined dashboard (built with Streamlit) for analysis and decision-making.

The focus is on creating a **scalable, secure, and modular pipeline** that supports future growth (additional data sources, increased volume) while ensuring data accuracy (including mechanisms for **backfilling** historical data to fill any gaps).

---

## Project Objectives
- **Automate Data Ingestion:** Eliminate manual data collection by scheduling a nightly pipeline that reliably fetches data from all required sources.
- **Ensure Timely Updates:** Provide fresh data every morning so that analysts and stakeholders can make decisions based on the latest information (e.g., the pipeline completes by 6 AM daily).
- **Integrate Multiple Sources:** Unify data from disparate providers (APIs, databases, files, etc.) into a **single cohesive schema**, giving a holistic view of the information in one place.
- **Improve Data Quality and Consistency:** Enforce validation and cleaning so that the stored data is accurate, consistent, and free of duplicates or gaps. Include the ability to backfill historical data to maintain a complete dataset.
- **Scalable & Extensible Design:** Build the pipeline with a modular architecture that can easily **extend to new data sources** or increased data volumes without significant refactoring.
- **User Accessibility:** Deliver data to end users via an accessible interface (Streamlit dashboard) with appropriate **authentication and role-based access**, so data remains secure but readily available to authorized users.
- **Operational Transparency:** Provide logging, error handling, and alerting such that the engineering team can monitor pipeline health and quickly address issues (failed runs, data discrepancies, etc.).

---

## Target Users
- **Data Analysts & Scientists:** Primary consumers of the integrated data. They will use the Streamlit dashboard or query the database directly to derive insights, perform analysis, and drive business decisions.
- **Business Stakeholders:** Managers or decision-makers who rely on daily reports/metrics. They benefit from the up-to-date dashboard without needing to manually compile data.
- **Data Engineers / IT Team:** The team responsible for maintaining the pipeline. They require tools for monitoring pipeline executions, troubleshooting issues, and performing maintenance (such as triggering a backfill or adding a new data source).
- **System Administrators:** Individuals who manage user access and system configuration. They ensure the pipeline’s resources (Azure Functions, databases, etc.) are running smoothly and securely, and may handle secrets or credentials management for external data providers.

---

## Functional Requirements
- **Nightly Automated Run:** The pipeline shall **execute automatically on a nightly schedule** (e.g., every day at midnight). This scheduler will trigger the data ingestion process without manual intervention.
- **Multiple Data Source Ingestion:** The system shall connect to and retrieve data from all configured external sources. Each source’s integration is handled through a modular provider component and should support **API keys or credentials** as needed.
- **Data Transformation & Cleaning:** The pipeline shall perform any necessary transformations on incoming data. This includes parsing or converting formats, data type conversions, handling missing values, and applying business rules for cleaning. If multiple sources provide overlapping data, the pipeline should merge or reconcile them (following predefined logic).
- **Centralized Data Storage:** All processed data shall be stored in a relational database (e.g., **Azure SQL Managed Instance** or equivalent). The pipeline should upsert or append new records each night without duplicating existing data.
- **Historical Backfill:** The pipeline shall support a mode to **backfill historical data** by running for a specified past date range to populate the database with data from days prior to the pipeline’s introduction (or to fill gaps caused by past failures).
- **Data Quality Validation:** The system shall validate data at critical points. If a data source returns an empty or malformed dataset, the pipeline should detect it and flag an error (possibly skipping that source’s data and continuing with others). Validation examples: schema checks, volume checks, range checks.
- **Error Handling & Notifications:** On runtime errors (API failures, DB errors), the pipeline shall catch exceptions, log detailed error information, and notify the support team. The system should support reruns of the pipeline (or parts of it) after issues are resolved.
- **Logging and Audit Trail:** Every run shall produce logs capturing start/end time, records fetched per source, errors/warnings, and confirmation of data stored. Optionally a **run history table** records each pipeline run status and timestamp.
- **Configuration Management:** The pipeline shall use external configuration for non-code settings such as active sources, API endpoints, credentials references, and tunable parameters (timeouts, batch sizes). Adding a source should mostly be config + provider module, not core code changes.
- **Data Access & Dashboard:** Provide a **Streamlit dashboard** that allows authorized users to view and interact with the latest data. It should support basic filtering/querying and downloads (CSV).
- **Role-Based Access Control:** Enforce access control so only authenticated users can access. Different actions restricted by role (admins vs analysts).
- **Modularity for New Data Sources:** Adding a new provider should require implementing a new adapter and minimal config changes; the orchestrator should dynamically include new providers that follow the interface.
- **Scalability for Data Volume:** The design must handle growth in sources and volume; leverage parallelism and batch processing as needed.
- **Security Considerations:** No hard-coded secrets. Secrets stored in vault/secure settings. Encrypt data in transit and at rest. Use least privilege for identities.
- **Compliance and Audit:** Keep traceability: when data was ingested and from which source. Maintain record lineage metadata.
- **Performance Benchmarks:** Target completion inside the nightly window (e.g., <2 hours), using incremental fetch where possible.

---

## Non-functional Requirements
- **Reliability & Recovery:** Implement retry logic and graceful failure handling. Support backfills to recover missed runs.
- **Performance:** Optimize for incremental fetch, vectorized transforms, batch DB writes, and concurrency where appropriate.
- **Scalability:** Scale out via serverless compute and scale DB compute as needed; plan for parallel provider execution.
- **Security:** Use Key Vault/secret manager, encrypted transport, and hardened network access. Restrict access by RBAC.
- **Maintainability:** Modular codebase, clear interfaces, config-driven behavior, tests, docs, and consistent logging.
- **Extensibility:** Designed for new providers, new processing stages, and new outputs without rewrites.
- **Usability:** Dashboard should be clear and functional; operational views should be understandable.
- **Compliance & Governance:** Respect data-provider terms, maintain auditability, and implement retention policies where required.
- **Availability:** Dashboard should be available for historical access; ensure backups and resilient deployments.
- **Observability:** Use metrics/logs/traces and alerts for failures and anomalous runtime/volume changes.

---

## System Architecture Overview

### High-Level Architecture
**Flow:** External Data Sources → Ingestion (Providers) → (Optional) Raw/Staging Storage → Transform & Validate → Central DB → Streamlit Dashboard

### Modularity and Data Source Abstraction
- Providers implement a common interface (e.g., `fetch_data(date)` returning standardized structures).
- Orchestrator reads configuration to determine which providers run.
- Providers encapsulate authentication, pagination, parsing, and source-specific quirks.
- Orchestrator catches per-provider failures; supports parallelism (threads/async or multi-function fanout).

### Backfill Support
- Treat pipeline as `pipeline(date)` so any date can be reprocessed.
- Support initial historical load and targeted backfills.
- Ensure idempotency via unique keys and upsert semantics.
- Differentiate backfill runs in logs and run metadata.

### System Components
- **Orchestration:** Azure Functions Timer Trigger (or equivalent).
- **Optional Raw Archive:** Azure Blob / object storage for raw payloads and staging.
- **Target Storage:** Azure SQL MI (or equivalent relational DB).
- **UI:** Streamlit app querying the DB.
- **Monitoring:** Application Insights / cloud monitoring + alerts.

---

## Database Schema (V1 Template)
The schema should support:
- Source lineage (which provider produced what).
- Time-series and entity-based querying (date range, ticker/entity filters).
- Efficient upserts and indexing.
- Run metadata to link stored records to pipeline runs.

**Recommended logical tables:**
- `dim_source` — provider metadata
- `dim_instrument` (optional for asset universe) — ticker, exchange, asset_type, status
- `fact_prices` / `fact_ohlcv` — daily OHLCV (raw + adjusted) keyed by instrument + date
- `fact_macro_series` — FRED/BLS series keyed by series_id + date
- `fact_feature` — engineered features keyed by instrument + date + feature_name
- `feature_diagnostic` — feature quality metrics such as IC and hit rate
- `pipeline_run` — run-level logs and metrics (status, duration, rows inserted/updated, error text)

**Indexing guidelines:**
- Composite keys on (instrument_id, trade_date) for price tables.
- (series_id, date) for macro series.
- (instrument_id, date, feature_name) for feature tables.
- Add date indexes where date filtering is common.

*(Specific columns and constraints are expected to be finalized during implementation once provider and feature catalog is defined.)*

---

## User Roles and Authentication Requirements

### Roles
| Role | Permissions |
|---|---|
| **Administrator** | Full access to pipeline controls, configuration, backfills, and all data. |
| **Data Engineer** | Operational access (logs, reruns, troubleshooting); may be same as Admin in small team. |
| **Analyst/Viewer** | Read-only access to dashboard and exports. |
| **Guest** (optional) | Limited demo access (future). |

### Authentication
- Minimum viable: **simple username/password** (basic auth) for dashboard.
- Preferred: Azure AD / SSO for enterprise-grade auth and group-based RBAC.
- Secrets stored in vault (Key Vault or equivalent).
- DB permissions separated for read vs write.

---

## Future Extensions and Modularity Planning
The architecture must support plug-in expansion, including:
- **Additional data sources** (Polygon, Tiingo, EODHistoricalData, Morningstar, FactSet, etc.).
- **Macro conditions dashboard** (growth/liquidity/risk appetite composites).
- **Backtesting module** for indicator testing and research workflows.
- **Portfolio optimization toolkit** for converting signals into portfolios.
- **API layer** for programmatic access (REST/GraphQL).
- **Data lake** outputs (parquet/Delta) for large-scale analytics.
- **More advanced monitoring** and run lineage.

Key design principle: new modules should bolt on via **standardized data contracts** (schemas + interfaces) rather than ad-hoc data handling.

---

## Appendices
- **Config conventions:** config-driven providers, environments, secrets references.
- **Run conventions:** normal nightly runs vs backfills; idempotency; rerun behavior.
- **Data contracts:** define canonical dataframes/records per domain (prices, macro, features).
