# AGENTS.md

## Cursor Cloud specific instructions

### Overview

ATLAS V1 is a Python-based nightly data pipeline for investment management. It uses Poetry for dependency management, SQLite for local dev, and Streamlit for the dashboard.

### Running services

- **CLI**: `poetry run atlas <command>` — see `README.md` "CLI Commands" for the full list.
- **Dashboard**: `ATLAS_ENV=development ATLAS_DB_CONNECTION=sqlite:///atlas_dev.db poetry run streamlit run src/atlas/dashboard/app.py --server.headless true --server.port 8501` — default login: `admin` / `atlas123`.
- **DB init**: `ATLAS_ENV=development ATLAS_DB_CONNECTION=sqlite:///atlas_dev.db poetry run python -c "from atlas.storage.database import get_database; db = get_database(); db.create_tables()"` (the CLI `atlas init-db` also works but avoid `--force` in non-interactive shells since it prompts for confirmation).

### Lint / type-check / test

- **Lint**: `poetry run ruff check src/`
- **Type check**: `poetry run mypy src/atlas/`
- **Tests**: `poetry run pytest` (the `tests/` directory is currently empty)

### Key gotchas

- The project venv is in-project at `.venv/`. Poetry is configured with `virtualenvs.in-project = true`.
- `ATLAS_DB_CONNECTION` env var must be set to `sqlite:///atlas_dev.db` for local dev; otherwise the app falls back to it but logs warnings about Key Vault failures.
- `ATLAS_ENV=development` loads `config/environments/development.yaml` which disables App Insights, raw archiving, and uses SQLite.
- API keys (`TIINGO_API_KEY`, `FRED_API_KEY`) are needed only to run the actual data pipeline (`atlas run`), not for lint/tests/dashboard.
- The `atlas init-db --force` subcommand has an interactive `typer.confirm()` prompt; avoid it in non-interactive contexts (use the Python snippet above instead).
- `PATH` must include `$HOME/.local/bin` for the `poetry` binary installed via pip.
- **SQLite + BigInteger autoincrement bug**: The `PipelineRun` model uses `BigInteger` for `run_id`, which does not auto-increment in SQLite (only exact `INTEGER` type supports `ROWID` aliasing). The `atlas run` CLI command will fail with `NOT NULL constraint failed: pipeline_run.run_id`. Workaround: insert pipeline runs with explicit IDs via raw SQL or `__table__.insert().values(run_id=N, ...)`, then call providers directly. The same issue affects `FeatureDiagnosticRecord.diagnostic_id`.
- **typer/click version conflict**: `atlas run --help` crashes with `TypeError: Parameter.make_metavar() missing 1 required positional argument: 'ctx'` due to typer 0.9 + latest click incompatibility. The actual CLI commands still parse and route correctly; only `--help` rendering is broken. Workaround: call pipeline code directly via Python instead of the CLI for `run`/`backfill` commands.
